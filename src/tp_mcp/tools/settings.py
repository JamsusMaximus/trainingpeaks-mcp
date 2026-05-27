"""Athlete settings tools: zones, FTP, thresholds, nutrition."""

import logging
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from tp_mcp.client import TPClient
from tp_mcp.tools._validation import format_validation_error

logger = logging.getLogger("tp-mcp")

POWER_ZONE_LABELS = [
    "Recovery",
    "Endurance",
    "Tempo",
    "Threshold",
    "VO2 Max",
    "Anaerobic Capacity",
]
POWER_ZONE_MAXIMUM = 2000


class FTPInput(BaseModel):
    """Validates FTP input."""

    ftp: int = Field(gt=0, le=2000)


class HRZonesInput(BaseModel):
    """Validates HR zones input."""

    threshold_hr: int | None = Field(default=None, gt=50, le=250)
    max_hr: int | None = Field(default=None, gt=50, le=250)
    resting_hr: int | None = Field(default=None, gt=20, le=120)
    workout_type: str = Field(default="general")

    @field_validator("workout_type")
    @classmethod
    def check_type(cls, v: str) -> str:
        if v not in ("general", "bike"):
            raise ValueError("workout_type must be 'general' or 'bike'")
        return v


class SpeedZonesInput(BaseModel):
    """Validates speed zones input."""

    run_threshold_pace: str | None = None
    swim_threshold_pace: str | None = None

    @field_validator("run_threshold_pace", "swim_threshold_pace")
    @classmethod
    def check_pace_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.match(r"^\d{1,2}:\d{2}(/\w+)?$", v):
            raise ValueError(f"Invalid pace format '{v}'. Use 'M:SS' (e.g. '4:30/km' or '1:45/100m')")
        return v


def _parse_pace_to_ms(pace_str: str, is_swim: bool = False) -> float:
    """Parse a pace string to metres per second.

    Args:
        pace_str: Pace like '4:30/km' or '1:45/100m'.
        is_swim: Whether this is a swim pace (per 100m).

    Returns:
        Speed in metres per second.
    """
    # Strip unit suffix if present
    pace_part = pace_str.split("/")[0]
    parts = pace_part.split(":")
    minutes = int(parts[0])
    seconds = int(parts[1])
    total_seconds = minutes * 60 + seconds

    if total_seconds == 0:
        raise ValueError(f"Invalid pace: {pace_str}")

    if is_swim:
        return 100.0 / total_seconds
    return 1000.0 / total_seconds


def _format_pace_min_km(speed_ms: float) -> str:
    """Format metres per second as min/km."""
    if speed_ms <= 0:
        return ""
    sec_per_km = 1000.0 / speed_ms
    minutes, seconds = divmod(int(round(sec_per_km)), 60)
    return f"{minutes}:{seconds:02d}/km"


def _format_pace_min_100m(speed_ms: float) -> str:
    """Format metres per second as min/100m."""
    if speed_ms <= 0:
        return ""
    sec_per_100m = 100.0 / speed_ms
    minutes, seconds = divmod(int(round(sec_per_100m)), 60)
    return f"{minutes}:{seconds:02d}/100m"


def _summarize_zone_ranges(group: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract privacy-safe zone ranges from a TrainingPeaks zone group."""
    zones = group.get("zones")
    if not isinstance(zones, list):
        return []

    summarized: list[dict[str, Any]] = []
    for idx, zone in enumerate(zones, start=1):
        if not isinstance(zone, dict):
            continue
        minimum = zone.get("minimum", zone.get("min"))
        maximum = zone.get("maximum", zone.get("max"))
        entry: dict[str, Any] = {"label": str(zone.get("label") or idx)}
        if isinstance(minimum, (int, float)):
            entry["min"] = round(float(minimum), 3)
        if isinstance(maximum, (int, float)):
            entry["max"] = round(float(maximum), 3)
        if "min" in entry or "max" in entry:
            summarized.append(entry)
    return summarized


def _summarize_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Extract a privacy-safe summary from athlete settings.

    The summary intentionally includes only training thresholds and zone ranges.
    It omits raw settings/profile/account fields that may contain identity data.
    """
    sport_by_id = {0: "general", 1: "swim", 2: "bike", 3: "run"}
    summary: dict[str, Any] = {}

    hr_zones = data.get("heartRateZones")
    if isinstance(hr_zones, list):
        for group in hr_zones:
            if not isinstance(group, dict):
                continue
            threshold = group.get("threshold")
            if not isinstance(threshold, (int, float)) or threshold <= 0:
                continue
            workout_type_id = group.get("workoutTypeId")
            sport = sport_by_id.get(workout_type_id, "other") if isinstance(workout_type_id, int) else "other"
            key = "lthr_bpm" if sport in ("general", "other") else f"lthr_bpm_{sport}"
            summary.setdefault(key, int(threshold))
            zones = _summarize_zone_ranges(group)
            if zones:
                zone_key = "hr_zones" if sport in ("general", "other") else f"hr_zones_{sport}"
                summary.setdefault(zone_key, zones)

    speed_zones = data.get("speedZones")
    if isinstance(speed_zones, list):
        for group in speed_zones:
            if not isinstance(group, dict):
                continue
            threshold = group.get("threshold")
            if not isinstance(threshold, (int, float)) or threshold <= 0:
                continue
            workout_type_id = group.get("workoutTypeId")
            sport = sport_by_id.get(workout_type_id, "other") if isinstance(workout_type_id, int) else "other"
            entry: dict[str, Any] = {"threshold_m_per_s": round(float(threshold), 3)}
            if sport == "swim":
                entry["pace_min_per_100m"] = _format_pace_min_100m(float(threshold))
            else:
                entry["pace_min_per_km"] = _format_pace_min_km(float(threshold))
            key = f"lt_pace_{sport}" if sport != "other" else "lt_pace_other"
            summary.setdefault(key, entry)

    power_zones = data.get("powerZones")
    if isinstance(power_zones, list):
        for group in power_zones:
            if not isinstance(group, dict):
                continue
            threshold = group.get("threshold")
            if not isinstance(threshold, (int, float)) or threshold <= 0:
                continue
            workout_type_id = group.get("workoutTypeId")
            sport = sport_by_id.get(workout_type_id, "other") if isinstance(workout_type_id, int) else "other"
            key = "ftp_watts" if sport in ("general", "other") else f"ftp_watts_{sport}"
            summary.setdefault(key, int(threshold))
            zones = _summarize_zone_ranges(group)
            if zones:
                zone_key = "power_zones" if sport in ("general", "other") else f"power_zones_{sport}"
                summary.setdefault(zone_key, zones)

    return summary


async def _fetch_athlete_settings() -> dict[str, Any]:
    """Fetch raw athlete settings or return an MCP-style error dict."""
    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v1/athletes/{athlete_id}/settings"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        if not response.data or not isinstance(response.data, dict):
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "No settings data returned.",
            }

        return response.data


async def tp_get_athlete_settings() -> dict[str, Any]:
    """Get athlete settings including FTP, thresholds, zones, and profile.

    Returns:
        Dict with all athlete settings.
    """
    settings = await _fetch_athlete_settings()
    if settings.get("isError"):
        return settings
    return {"settings": settings}


async def tp_get_athlete_settings_summary() -> dict[str, Any]:
    """Get only a privacy-safe athlete settings summary."""
    settings = await _fetch_athlete_settings()
    if settings.get("isError"):
        return settings
    return {"summary": _summarize_settings(settings)}


async def tp_update_ftp(ftp: int) -> dict[str, Any]:
    """Update FTP and recalculate the athlete's default power zones.

    Args:
        ftp: Functional Threshold Power in watts.

    Returns:
        Dict with updated zones or error.
    """
    try:
        params = FTPInput(ftp=ftp)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        settings_endpoint = f"/fitness/v1/athletes/{athlete_id}/settings"
        settings_response = await client.get(settings_endpoint)
        if settings_response.is_error:
            return {
                "isError": True,
                "error_code": settings_response.error_code.value if settings_response.error_code else "API_ERROR",
                "message": settings_response.message,
            }

        if not settings_response.data or not isinstance(settings_response.data, dict):
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "No settings data returned.",
            }

        power_zones = settings_response.data.get("powerZones")
        if not isinstance(power_zones, list) or not power_zones:
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "No power zones found in athlete settings.",
            }

        target_index = next(
            (idx for idx, zone_group in enumerate(power_zones)
             if isinstance(zone_group, dict) and zone_group.get("workoutTypeId") == 0),
            0,
        )
        target_zone_group = power_zones[target_index]
        if not isinstance(target_zone_group, dict):
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "Unexpected power zone format returned by TrainingPeaks.",
            }

        existing_labels = []
        existing_zones = target_zone_group.get("zones")
        if isinstance(existing_zones, list):
            existing_labels = [
                zone.get("label")
                for zone in existing_zones
                if isinstance(zone, dict) and zone.get("label")
            ]
        labels = existing_labels if len(existing_labels) == len(POWER_ZONE_LABELS) else POWER_ZONE_LABELS

        current_threshold = target_zone_group.get("threshold")
        zone_maxima: list[int] = []
        if isinstance(current_threshold, (int, float)) and current_threshold > 0 and isinstance(existing_zones, list):
            existing_maxima: list[int] = []
            for zone in existing_zones[:-1]:
                if not isinstance(zone, dict):
                    existing_maxima = []
                    break
                maximum = zone.get("maximum")
                if not isinstance(maximum, (int, float)):
                    existing_maxima = []
                    break
                existing_maxima.append(int(maximum))
            if len(existing_maxima) == len(labels) - 1:
                zone_maxima = [round(params.ftp * (maximum / current_threshold)) for maximum in existing_maxima]

        if not zone_maxima:
            zone_maxima = [
                round(params.ftp * ratio)
                for ratio in (0.56, 0.76, 0.91, 1.06, 1.21)
            ]
        zones = []
        lower_bound = 0
        for label, upper_bound in zip(labels[:-1], zone_maxima, strict=False):
            zones.append({
                "label": label,
                "minimum": lower_bound,
                "maximum": upper_bound,
            })
            lower_bound = upper_bound + 1
        zones.append({
            "label": labels[-1],
            "minimum": lower_bound,
            "maximum": POWER_ZONE_MAXIMUM,
        })

        updated_zone_group = {
            "threshold": params.ftp,
            "calculationMethod": target_zone_group.get("calculationMethod"),
            "workoutTypeId": target_zone_group.get("workoutTypeId"),
            "zones": zones,
        }
        if "zoneCalculatorId" in target_zone_group:
            updated_zone_group["zoneCalculatorId"] = target_zone_group.get("zoneCalculatorId")

        payload = list(power_zones)
        payload[target_index] = updated_zone_group

        endpoint = f"/fitness/v2/athletes/{athlete_id}/powerzones"
        response = await client.put(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {
            "success": True,
            "ftp": params.ftp,
            "workout_type_id": updated_zone_group["workoutTypeId"],
            "zones": zones,
        }


async def tp_update_hr_zones(
    threshold_hr: int | None = None,
    max_hr: int | None = None,
    resting_hr: int | None = None,
    workout_type: str = "general",
) -> dict[str, Any]:
    """Update heart rate zones.

    Args:
        threshold_hr: Threshold heart rate (optional).
        max_hr: Maximum heart rate (optional).
        resting_hr: Resting heart rate (optional).
        workout_type: 'general' or 'bike' (default 'general').

    Returns:
        Dict with updated zones or error.
    """
    try:
        params = HRZonesInput(
            threshold_hr=threshold_hr,
            max_hr=max_hr,
            resting_hr=resting_hr,
            workout_type=workout_type,
        )
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    if params.threshold_hr is None and params.max_hr is None and params.resting_hr is None:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "At least one of threshold_hr, max_hr, or resting_hr must be provided.",
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        payload: dict[str, Any] = {}
        if params.threshold_hr is not None:
            payload["threshold"] = params.threshold_hr
        if params.max_hr is not None:
            payload["maximum"] = params.max_hr
        if params.resting_hr is not None:
            payload["resting"] = params.resting_hr

        endpoint = f"/fitness/v2/athletes/{athlete_id}/heartratezones"
        response = await client.put(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {
            "success": True,
            "message": "Heart rate zones updated.",
            "updates": payload,
        }


async def tp_update_speed_zones(
    run_threshold_pace: str | None = None,
    swim_threshold_pace: str | None = None,
) -> dict[str, Any]:
    """Update speed/pace zones.

    Args:
        run_threshold_pace: Run threshold pace (e.g. '4:30/km').
        swim_threshold_pace: Swim threshold pace (e.g. '1:45/100m').

    Returns:
        Dict with updated zones or error.
    """
    try:
        params = SpeedZonesInput(
            run_threshold_pace=run_threshold_pace,
            swim_threshold_pace=swim_threshold_pace,
        )
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    if params.run_threshold_pace is None and params.swim_threshold_pace is None:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "At least one of run_threshold_pace or swim_threshold_pace must be provided.",
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        payload: dict[str, Any] = {}

        if params.run_threshold_pace is not None:
            try:
                speed_ms = _parse_pace_to_ms(params.run_threshold_pace)
                payload["runThreshold"] = speed_ms
            except ValueError as e:
                return {
                    "isError": True,
                    "error_code": "VALIDATION_ERROR",
                    "message": str(e),
                }

        if params.swim_threshold_pace is not None:
            try:
                speed_ms = _parse_pace_to_ms(params.swim_threshold_pace, is_swim=True)
                payload["swimThreshold"] = speed_ms
            except ValueError as e:
                return {
                    "isError": True,
                    "error_code": "VALIDATION_ERROR",
                    "message": str(e),
                }

        endpoint = f"/fitness/v2/athletes/{athlete_id}/speedzones"
        response = await client.put(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {
            "success": True,
            "message": "Speed zones updated.",
            "updates": payload,
        }


async def tp_update_nutrition(planned_calories: int) -> dict[str, Any]:
    """Update nutrition settings.

    Args:
        planned_calories: Planned daily calories.

    Returns:
        Dict with confirmation or error.
    """
    if planned_calories < 0 or planned_calories > 20000:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "planned_calories must be between 0 and 20000.",
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v1/athletes/{athlete_id}/nutritionsettings"
        payload = {"plannedCalories": planned_calories}
        response = await client.post(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {
            "success": True,
            "planned_calories": planned_calories,
        }


async def tp_get_pool_length_settings() -> dict[str, Any]:
    """Get pool length settings.

    Returns:
        Dict with pool length options and default.
    """
    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v1/athletes/{athlete_id}/poollengthsettings"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {"pool_length_settings": response.data}
