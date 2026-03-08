"""Tool for workout analysis via the Peaksware analysis API."""

import json
import logging
import tempfile
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


def _save_analysis_json(workout_id: int, data: dict[str, Any]) -> str:
    """Save full analysis data to a JSON file.

    Returns:
        Absolute path to the saved file.
    """
    ANALYSIS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    filepath = ANALYSIS_DATA_DIR / f"workout_{workout_id}.json"
    filepath.write_text(json.dumps(data, indent=2))
    return str(filepath)


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
        # so we make a direct httpx call with the Bearer token.
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/json",
            "Origin": "https://app.trainingpeaks.com",
            "Referer": "https://app.trainingpeaks.com/",
        }

        try:
            async with httpx.AsyncClient(timeout=ANALYSIS_TIMEOUT) as http_client:
                response = await http_client.post(
                    f"{ANALYSIS_API_BASE}/workout-analysis/v1/analyze",
                    headers=headers,
                    json={"workoutId": wid, "viewingPersonId": athlete_id},
                )
        except httpx.TimeoutException:
            return {
                "isError": True,
                "error_code": "NETWORK_ERROR",
                "message": "Analysis request timed out.",
            }
        except httpx.RequestError:
            logger.exception("Network error during workout analysis")
            return {
                "isError": True,
                "error_code": "NETWORK_ERROR",
                "message": "A network error occurred.",
            }

        if response.status_code == 401:
            return {
                "isError": True,
                "error_code": "AUTH_EXPIRED",
                "message": "Session expired. Run 'tp-mcp auth' to re-authenticate.",
            }
        if response.status_code == 404:
            return {
                "isError": True,
                "error_code": "NOT_FOUND",
                "message": f"Workout {workout_id} not found for analysis.",
            }
        if response.status_code != 200:
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": f"Analysis API error: {response.status_code}",
            }

        try:
            raw_data = response.json()
        except Exception:
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "Failed to parse analysis response.",
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
    totals = {t.name: {"value": t.value, "unit": t.unit} for t in analysis.totals}

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
        "totals": totals,
        "dataChannels": channels,
        "lapData": analysis.lap_data,
        "lapColumns": analysis.lap_columns,
        "time_series_points": len(analysis.data),
        "data_file": data_file,
    }
