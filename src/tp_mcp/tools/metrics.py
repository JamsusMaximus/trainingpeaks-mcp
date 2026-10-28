"""Health metrics tools: log, get, nutrition."""

import logging
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from tp_mcp.client import TPClient
from tp_mcp.tools._validation import DateRangeInput, format_validation_error

logger = logging.getLogger("tp-mcp")

# Metric type IDs (confirmed from network captures)
METRIC_TYPES: dict[str, dict[str, Any]] = {
    "pulse": {"type": 5, "label": "Pulse", "units": "bpm", "formatedUnits": "bpm", "min": 10, "max": 200},
    "weight_kg": {"type": 9, "label": "Weight", "units": "kg", "formatedUnits": "kg", "min": 0, "max": 1000},
    "rmr": {"type": 15, "label": "RMR", "units": "kcal", "formatedUnits": "kcal", "min": 500, "max": 5000},
    "injury": {"type": 23, "label": "Injury", "units": "", "formatedUnits": "", "min": 1, "max": 10},
    "sleep_hours": {"type": 6, "label": "Sleep", "units": "hours", "formatedUnits": "hours", "min": 0, "max": 72},
    "hrv": {"type": 60, "label": "HRV", "units": "", "formatedUnits": "", "min": 0, "max": 200},
    "spo2": {"type": 53, "label": "SPO2", "units": "%", "formatedUnits": "%", "min": 0, "max": 100},
    "steps": {"type": 58, "label": "Steps", "units": "steps", "formatedUnits": "steps", "min": 0, "max": 1000000000},
}


class LogMetricsInput(BaseModel):
    """Validates input for logging metrics."""

    date: str
    weight_kg: float | None = Field(default=None, ge=0, le=1000)
    pulse: int | None = Field(default=None, ge=10, le=200)
    hrv: float | None = Field(default=None, ge=0, le=200)
    sleep_hours: float | None = Field(default=None, ge=0, le=72)
    spo2: float | None = Field(default=None, ge=0, le=100)
    steps: int | None = Field(default=None, ge=0, le=1000000000)
    rmr: int | None = Field(default=None, ge=500, le=5000)
    injury: int | None = Field(default=None, ge=1, le=10)

    @field_validator("date")
    @classmethod
    def check_date(cls, v: str) -> str:
        from datetime import date

        date.fromisoformat(v)
        return v


async def tp_log_metrics(
    date: str,
    weight_kg: float | None = None,
    pulse: int | None = None,
    hrv: float | None = None,
    sleep_hours: float | None = None,
    spo2: float | None = None,
    steps: int | None = None,
    rmr: int | None = None,
    injury: int | None = None,
) -> dict[str, Any]:
    """Log health metrics for a date.

    Args:
        date: Date in ISO format (YYYY-MM-DD).
        weight_kg: Body weight in kg.
        pulse: Resting pulse in bpm.
        hrv: Heart rate variability.
        sleep_hours: Hours of sleep.
        spo2: Blood oxygen saturation (%).
        steps: Step count.
        rmr: Resting metabolic rate (kcal).
        injury: Injury level (1-10).

    Returns:
        Dict with confirmation or error.
    """
    try:
        params = LogMetricsInput(
            date=date,
            weight_kg=weight_kg,
            pulse=pulse,
            hrv=hrv,
            sleep_hours=sleep_hours,
            spo2=spo2,
            steps=steps,
            rmr=rmr,
            injury=injury,
        )
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    # Build details list from provided metrics
    metric_values: dict[str, float] = {}
    if params.weight_kg is not None:
        metric_values["weight_kg"] = params.weight_kg
    if params.pulse is not None:
        metric_values["pulse"] = float(params.pulse)
    if params.hrv is not None:
        metric_values["hrv"] = params.hrv
    if params.sleep_hours is not None:
        metric_values["sleep_hours"] = params.sleep_hours
    if params.spo2 is not None:
        metric_values["spo2"] = params.spo2
    if params.steps is not None:
        metric_values["steps"] = float(params.steps)
    if params.rmr is not None:
        metric_values["rmr"] = float(params.rmr)
    if params.injury is not None:
        metric_values["injury"] = float(params.injury)

    if not metric_values:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "At least one metric must be provided.",
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        details = []
        for key, value in metric_values.items():
            meta = METRIC_TYPES[key]
            details.append({
                "type": meta["type"],
                "label": meta["label"],
                "value": value,
                "time": f"{params.date}T12:00:00",
                "temporaryId": 0,
                "units": meta["units"],
                "formatedUnits": meta["formatedUnits"],
                "min": meta["min"],
                "max": meta["max"],
            })

        payload = {
            "athleteId": athlete_id,
            "timeStamp": f"{params.date}T00:00:00",
            "id": None,
            "details": details,
        }

        endpoint = f"/metrics/v3/athletes/{athlete_id}/consolidatedtimedmetric"
        response = await client.post(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {
            "success": True,
            "date": params.date,
            "logged": list(metric_values.keys()),
        }


# Labels whose snake_case form would be ambiguous on its own. Everything else
# is derived mechanically from the label TrainingPeaks attaches to the detail.
_COMPACT_LABEL_OVERRIDES: dict[str, str] = {
    "sleep": "sleep_hours",  # type 6, hours - matches the tp_log_metrics parameter name
}


def _metric_column(label: Any, metric_type: Any) -> str:
    """Derive a stable snake_case column name from a metric detail's label."""
    text = str(label or "").strip()
    if not text:
        return f"type_{metric_type}"
    lowered = text.lower()
    if lowered in _COMPACT_LABEL_OVERRIDES:
        return _COMPACT_LABEL_OVERRIDES[lowered]
    column = re.sub(r"[^0-9a-z]+", "_", lowered).strip("_")
    if not column:
        return f"type_{metric_type}"
    if column[0].isdigit():
        column = f"m_{column}"
    return column


def _compact_metrics(days: list[Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Flatten TP's consolidated metric days into one row per day.

    Each detail becomes a ``{column: value}`` pair keyed by its snake_cased
    label; the per-detail wrapper (``parentId``, ``uploadClient``,
    ``modifiedTime``, ``type``, ``isPotentiallyNegative``, ``time``) is
    dropped. Values are passed through untouched (some metrics are lists).
    If a label repeats within a day the last value wins.

    Returns:
        ``(rows, labels)`` where ``labels`` maps each column back to the
        original TrainingPeaks label.
    """
    rows: list[dict[str, Any]] = []
    labels: dict[str, str] = {}
    for day in days:
        if not isinstance(day, dict):
            continue
        stamp = str(day.get("timeStamp") or "")
        row: dict[str, Any] = {"date": stamp.split("T")[0] if stamp else None}
        for detail in day.get("details") or []:
            if not isinstance(detail, dict):
                continue
            column = _metric_column(detail.get("label"), detail.get("type"))
            labels.setdefault(column, str(detail.get("label") or column))
            row[column] = detail.get("value")
        rows.append(row)
    return rows, labels


async def tp_get_metrics(start_date: str, end_date: str, compact: bool = False) -> dict[str, Any]:
    """Get health metrics for a date range.

    Args:
        start_date: Start date in ISO format (YYYY-MM-DD).
        end_date: End date in ISO format (YYYY-MM-DD).
        compact: When true, return one row per day with a snake_cased column
            per metric label (hrv, pulse, sleep_hours, weight, body_battery,
            ...) instead of TP's per-detail wrapper objects. Default output is
            unchanged.

    Returns:
        Dict with per-day metric values.
    """
    try:
        params = DateRangeInput(start_date=start_date, end_date=end_date)
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

        start_str = params.start_date.isoformat()
        end_str = params.end_date.isoformat()
        endpoint = f"/metrics/v3/athletes/{athlete_id}/consolidatedtimedmetrics/{start_str}/{end_str}"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        if not response.data:
            return {
                "metrics": [],
                "count": 0,
                "message": "No metrics data for this date range.",
            }

        days = response.data if isinstance(response.data, list) else [response.data]

        if compact:
            rows, labels = _compact_metrics(days)
            return {
                "metrics": rows,
                "count": len(rows),
                "date_range": {"start": start_date, "end": end_date},
                "compact": True,
                "labels": labels,
            }

        return {
            "metrics": days,
            "count": len(days),
            "date_range": {"start": start_date, "end": end_date},
        }


async def tp_get_nutrition(start_date: str, end_date: str) -> dict[str, Any]:
    """Get nutrition data for a date range.

    Args:
        start_date: Start date in ISO format (YYYY-MM-DD).
        end_date: End date in ISO format (YYYY-MM-DD).

    Returns:
        Dict with nutrition data.
    """
    try:
        params = DateRangeInput(start_date=start_date, end_date=end_date)
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

        start_str = params.start_date.isoformat()
        end_str = params.end_date.isoformat()
        endpoint = f"/fitness/v1/athletes/{athlete_id}/nutrition/{start_str}/{end_str}"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        if not response.data:
            return {
                "nutrition": [],
                "count": 0,
                "message": "No nutrition data for this date range.",
            }

        return {
            "nutrition": response.data if isinstance(response.data, list) else [response.data],
            "count": len(response.data) if isinstance(response.data, list) else 1,
            "date_range": {"start": start_date, "end": end_date},
        }
