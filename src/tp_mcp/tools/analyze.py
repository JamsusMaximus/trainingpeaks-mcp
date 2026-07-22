"""Tool for workout analysis via the Peaksware analysis API.

TrainingPeaks retired the monolithic v1 endpoint
(``POST /workout-analysis/v1/analyze``) — confirmed dead 2026-07 (every
workout, every account, every age, 404 with an empty body from the real
backend, not the gateway — auth was never the issue). Live browser-network
tracing showed the current web app instead calls three narrower v2
endpoints per workout:

  * ``POST /workout-analysis/v2/analyze/summary`` — whole-workout totals
    (TSS/IF/NP/EF/decoupling/...).
  * ``POST /workout-analysis/v2/analyze/charts``  — per-second time-series
    plus per-channel min/max/average/zones.
  * ``POST /workout-analysis/v2/analyze/laps``    — device-recorded laps
    (WorkoutStepIndex/Intensity/LapTrigger/AveragePace/...).

All three take a body of just ``{"workoutId": <id>}`` — no
``viewingPersonId`` needed even for a coach viewing an athlete's workout
(verified live: the workout id alone is sufficient, confirmed with and
without the field for a coach-owned athlete).

The three responses are merged back into the same shape the rest of this
codebase (and any downstream consumer) already expects from
``parse_workout_analysis`` — so only this fetch layer needed to change.
``summary`` is required (its absence means the workout genuinely isn't
analyzable, mirroring the old v1 404 semantics); ``charts``/``laps`` degrade
gracefully to empty on a 404 (some entries — e.g. manually logged, no device
file — legitimately lack per-second/lap data while still having totals).
"""

import json
import logging
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from tp_mcp.client import TPClient, parse_workout_analysis
from tp_mcp.tools._validation import WorkoutIdInput, format_validation_error

logger = logging.getLogger("tp-mcp")

ANALYSIS_API_BASE = "https://api.peakswaresb.com"
ANALYSIS_TIMEOUT = 60.0
ANALYSIS_DATA_DIR = Path(tempfile.gettempdir()) / "tp-mcp" / "analysis"

_SUMMARY_PATH = "/workout-analysis/v2/analyze/summary"
_CHARTS_PATH = "/workout-analysis/v2/analyze/charts"
_LAPS_PATH = "/workout-analysis/v2/analyze/laps"


def _save_analysis_json(workout_id: int, data: dict[str, Any]) -> str:
    """Save full analysis data (including time-series) to a JSON file.

    Returns:
        Absolute path to the saved file.
    """
    ANALYSIS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    filepath = ANALYSIS_DATA_DIR / f"workout_{workout_id}.json"
    filepath.write_text(json.dumps(data, indent=2))
    return str(filepath)


def _error_for_status(status_code: int, workout_id: str) -> dict[str, Any] | None:
    """Map a non-200 analysis-API status to our error envelope, or None for 200."""
    if status_code == 401:
        return {
            "isError": True,
            "error_code": "AUTH_EXPIRED",
            "message": "Session expired. Run 'tp-mcp auth' to re-authenticate.",
        }
    if status_code == 404:
        return {
            "isError": True,
            "error_code": "NOT_FOUND",
            "message": f"Workout {workout_id} not found for analysis.",
        }
    if status_code != 200:
        return {
            "isError": True,
            "error_code": "API_ERROR",
            "message": f"Analysis API error: {status_code}",
        }
    return None


async def _post_analysis(
    http_client: httpx.AsyncClient,
    path: str,
    headers: dict[str, str],
    workout_id: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """POST ``{"workoutId": workout_id}`` to a v2 analysis endpoint.

    Returns:
        ``(body, None)`` on success, or ``(None, error_envelope)``.
    """
    try:
        response = await http_client.post(
            f"{ANALYSIS_API_BASE}{path}",
            headers=headers,
            json={"workoutId": workout_id},
        )
    except httpx.TimeoutException:
        return None, {
            "isError": True,
            "error_code": "NETWORK_ERROR",
            "message": "Analysis request timed out.",
        }
    except httpx.RequestError:
        logger.exception("Network error during workout analysis (%s)", path)
        return None, {
            "isError": True,
            "error_code": "NETWORK_ERROR",
            "message": "A network error occurred.",
        }

    err = _error_for_status(response.status_code, str(workout_id))
    if err:
        return None, err

    try:
        return response.json(), None
    except Exception:
        return None, {
            "isError": True,
            "error_code": "API_ERROR",
            "message": "Failed to parse analysis response.",
        }


def _stop_timestamp(start_iso: str | None, elapsed_seconds: Any) -> str | None:
    """v2's summary endpoint only gives ``startTimestamp`` — derive the stop
    from ``TotalElapsedTime`` (wall-clock elapsed, includes any pauses), to
    keep feeding the same start/stop pair the rest of the codebase expects
    (multisport-day ordering, gap detection, local-time display)."""
    if not start_iso or not isinstance(elapsed_seconds, (int, float)):
        return None
    try:
        start_dt = datetime.fromisoformat(start_iso)
    except ValueError:
        return None
    return (start_dt + timedelta(seconds=float(elapsed_seconds))).isoformat()


async def tp_analyze_workout(workout_id: str) -> dict[str, Any]:
    """Get detailed workout analysis including metrics, zones, and lap data.

    Full time-series data is saved to a JSON file for further analysis.

    Args:
        workout_id: The workout ID (from tp_get_workouts).

    Returns:
        Dict with totals, data channels, lap data, and path to full data file.
    """
    try:
        validated = WorkoutIdInput(workout_id=workout_id)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }
    wid = validated.workout_id

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        # Ensure we have a valid token (athlete_id may have come from cache
        # without triggering token exchange)
        token_result = await client._ensure_access_token()
        if not token_result.success:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": token_result.message or "Failed to obtain access token.",
            }

        access_token = client._token_cache.access_token
        if not access_token:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "No access token available. Re-authenticate.",
            }

        # Analysis API is on a different domain than the main TP API,
        # so we make direct httpx calls with the Bearer token.
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/json",
            "Origin": "https://app.trainingpeaks.com",
            "Referer": "https://app.trainingpeaks.com/",
        }

        async with httpx.AsyncClient(timeout=ANALYSIS_TIMEOUT) as http_client:
            summary, err = await _post_analysis(http_client, _SUMMARY_PATH, headers, wid)
            if err:
                return err

            charts, charts_err = await _post_analysis(http_client, _CHARTS_PATH, headers, wid)
            if charts_err:
                if charts_err.get("error_code") == "NOT_FOUND":
                    logger.info("workout %s: no chart/stream data available", wid)
                    charts = None
                else:
                    return charts_err

            laps, laps_err = await _post_analysis(http_client, _LAPS_PATH, headers, wid)
            if laps_err:
                if laps_err.get("error_code") == "NOT_FOUND":
                    logger.info("workout %s: no lap data available", wid)
                    laps = None
                else:
                    return laps_err

    summary_data = (summary or {}).get("data") or {}
    # Key totals by ``friendlyName`` (e.g. "NP", "Distance") rather than the v2
    # identifier (e.g. "NormalizedPower", "TotalDistance") to preserve the same
    # total names the old v1 endpoint returned; fall back to the identifier when
    # a channel has no friendlyName.
    totals = [
        {"name": meta.get("friendlyName") or name, "value": meta.get("value"), "unit": meta.get("unit")}
        for name, meta in summary_data.items()
        if isinstance(meta, dict)
    ]
    start_ts = (summary or {}).get("startTimestamp")
    elapsed = (summary_data.get("TotalElapsedTime") or {}).get("value")
    stop_ts = _stop_timestamp(start_ts, elapsed)

    charts_metadata = (charts or {}).get("metadata") or {}
    data_elements = [
        {
            "identifier": ident,
            "name": meta.get("friendlyName"),
            "unit": meta.get("unit"),
            "min": meta.get("minimum"),
            "max": meta.get("maximum"),
            "average": meta.get("average"),
            "zones": meta.get("zones"),
        }
        for ident, meta in charts_metadata.items()
        if isinstance(meta, dict)
    ]
    time_series = (charts or {}).get("data") or []

    lap_column_meta = (laps or {}).get("columnMetadata") or {}
    lap_columns = [
        {"identifier": ident, **meta}
        for ident, meta in lap_column_meta.items()
        if isinstance(meta, dict)
    ]
    lap_data = (laps or {}).get("data") or []

    raw_data: dict[str, Any] = {
        "workoutId": wid,
        "startTimestamp": start_ts,
        "stopTimestamp": stop_ts,
        "totals": totals,
        "dataElements": data_elements,
        "data": time_series,
        "lapData": lap_data,
        "lapColumns": lap_columns,
    }

    try:
        analysis = parse_workout_analysis(raw_data)
    except Exception:
        logger.exception("Failed to parse workout analysis")
        return {
            "isError": True,
            "error_code": "API_ERROR",
            "message": "Failed to parse workout analysis.",
        }

    # Save full raw data (including time-series) to file
    data_file = _save_analysis_json(wid, raw_data)

    # Return summary inline, point to file for full data
    totals_out = {t.name: {"value": t.value, "unit": t.unit} for t in analysis.totals}

    channels = [
        {
            k: v
            for k, v in {
                "identifier": ch.identifier,
                "name": ch.name,
                "unit": ch.unit,
                "min": ch.min,
                "max": ch.max,
                "average": ch.average,
                "zones": ch.zones,
            }.items()
            if v is not None
        }
        for ch in analysis.data_elements
    ]

    return {
        "workoutId": analysis.workout_id,
        "startTimestamp": analysis.start_timestamp,
        "stopTimestamp": analysis.stop_timestamp,
        "totals": totals_out,
        "dataChannels": channels,
        "lapData": analysis.lap_data,
        "lapColumns": analysis.lap_columns,
        "time_series_points": len(analysis.data),
        "data_file": data_file,
    }
