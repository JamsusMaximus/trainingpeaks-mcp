"""Workout tools: get, create, update, delete, copy, comments, reorder."""

import json
import logging
from datetime import date as date_type
from datetime import datetime as datetime_type
from typing import Any, Literal, NamedTuple

from pydantic import ValidationError

from tp_mcp.client import TPClient, parse_workout_detail, parse_workout_list
from tp_mcp.tools._validation import (
    CreateWorkoutInput,
    DateRangeInput,
    UpdateWorkoutInput,
    WorkoutIdInput,
    format_validation_error,
)
from tp_mcp.tools.structure import (
    build_wire_structure,
    compute_if_tss,
    parse_structure_input,
)

logger = logging.getLogger("tp-mcp")


class StructurePayload(NamedTuple):
    wire_structure: dict | None
    duration_minutes: float | None
    intensity_factor: float | None
    tss: float | None
    error: str | None


def _extract_file_infos(raw_data: dict, key: str) -> list[dict]:
    """Normalize TP workout file metadata arrays."""
    infos = raw_data.get(key)
    if not isinstance(infos, list):
        return []
    normalized = []
    for item in infos:
        if not isinstance(item, dict):
            continue
        file_id = item.get("fileId")
        normalized.append({
            "file_id": str(file_id) if file_id is not None else None,
            "file_system_id": item.get("fileSystemId"),
            "file_name": item.get("fileName"),
            "uploaded_at": item.get("dateUploaded"),
        })
    return normalized


def _prepare_structure_payload(
    structure: dict[str, Any] | str | None,
) -> StructurePayload:
    """Parse simplified structure input and derive TP payload values."""
    if structure is None:
        return StructurePayload(None, None, None, None, None)

    try:
        parsed_structure = parse_structure_input(structure)
        wire_structure = build_wire_structure(parsed_structure)
        structure_if, structure_tss, total_seconds = compute_if_tss(parsed_structure)
        return StructurePayload(
            wire_structure=wire_structure,
            duration_minutes=total_seconds / 60.0,
            intensity_factor=structure_if,
            tss=structure_tss,
            error=None,
        )
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return StructurePayload(None, None, None, None, f"Invalid structure: {msg}")


def _validate_structured_workout(structured_workout: dict[str, Any]) -> str | None:
    """Validate the minimum schema needed to round-trip TP native structures."""
    required = {
        "structure",
        "polyline",
        "primaryLengthMetric",
        "primaryIntensityMetric",
        "primaryIntensityTargetOrRange",
    }
    missing = required - set(structured_workout.keys())
    if missing:
        return (
            "structured_workout is missing required fields: "
            f"{', '.join(sorted(missing))}"
        )
    if not isinstance(structured_workout.get("structure"), list):
        return "structured_workout.structure must be a list."
    return None


def _encode_structured_workout(
    structured_workout: dict[str, Any] | None,
) -> tuple[str | None, str | None]:
    """Serialize a TP native workout structure for write endpoints."""
    if structured_workout is None:
        return None, None

    error = _validate_structured_workout(structured_workout)
    if error:
        return None, error

    try:
        return json.dumps(structured_workout), None
    except (TypeError, ValueError) as e:
        return None, f"structured_workout must be JSON-serializable: {e}"


def _decode_structured_workout(raw_structure: Any) -> dict[str, Any] | None:
    """Decode TP native workout structure from API responses."""
    if raw_structure is None:
        return None
    if isinstance(raw_structure, dict):
        return raw_structure
    if isinstance(raw_structure, str):
        try:
            parsed = json.loads(raw_structure)
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None

# Maps sport name to (workoutTypeFamilyId, workoutTypeValueId)
# IDs confirmed from GET /fitness/v6/workouttypes
SPORT_TYPE_MAP: dict[str, tuple[int, int]] = {
    "Swim": (1, 1),
    "Bike": (2, 2),
    "Run": (3, 3),
    "Brick": (4, 4),
    "Crosstrain": (5, 5),
    "Race": (6, 6),
    "DayOff": (7, 7),
    "MtnBike": (8, 8),
    "Strength": (9, 9),
    "Custom": (10, 10),
    "XCSki": (11, 11),
    "Rowing": (12, 12),
    "Walk": (13, 13),
    "Other": (100, 100),
}


def _format_workout_day(value: date_type | datetime_type) -> str:
    """Format a workout day value for the TrainingPeaks API."""
    day = value.date() if isinstance(value, datetime_type) else value
    return f"{day.isoformat()}T00:00:00"


def _format_start_time_planned(value: datetime_type) -> str:
    """Format a planned start time for the TrainingPeaks API."""
    return value.isoformat(timespec="seconds")


def _shift_start_time_planned(existing_start_time: str, target_day: date_type) -> str | None:
    """Move an existing planned start time to a new day, preserving its time-of-day."""
    try:
        start_dt = datetime_type.fromisoformat(existing_start_time)
    except ValueError:
        return None
    return datetime_type.combine(target_day, start_dt.timetz()).isoformat(timespec="seconds")


async def tp_get_workouts(
    start_date: str,
    end_date: str,
    workout_filter: Literal["all", "planned", "completed"] = "all",
) -> dict[str, Any]:
    """Get workouts for a date range.

    Args:
        start_date: Start date in ISO format (YYYY-MM-DD).
        end_date: End date in ISO format (YYYY-MM-DD).
        workout_filter: Filter by status - "all", "planned", or "completed".

    Returns:
        Dict with workouts list, count, and date_range.
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

        endpoint = f"/fitness/v6/athletes/{athlete_id}/workouts/{start_str}/{end_str}"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        if not response.data:
            return {
                "workouts": [],
                "count": 0,
                "date_range": {"start": start_date, "end": end_date},
            }

        try:
            workouts = parse_workout_list(response.data)

            # Apply filter
            if workout_filter == "planned":
                workouts = [w for w in workouts if not w.is_completed]
            elif workout_filter == "completed":
                workouts = [w for w in workouts if w.is_completed]

            # Convert to dict format for response
            workout_dicts = [
                {
                    "id": str(w.id),
                    "date": w.date.isoformat(),
                    "title": w.title,
                    "type": w.workout_status,
                    "sport": w.sport,
                    "duration_planned": w.duration_planned,
                    "duration_actual": w.duration_actual,
                    "distance_planned_km": w.distance_planned / 1000 if w.distance_planned else None,
                    "distance_actual_km": w.distance_actual / 1000 if w.distance_actual else None,
                    "tss": w.tss_actual or w.tss_planned,
                    "description": w.description,
                }
                for w in workouts
            ]

            return {
                "workouts": workout_dicts,
                "count": len(workout_dicts),
                "date_range": {"start": start_date, "end": end_date},
            }

        except Exception:
            logger.exception("Failed to parse workouts")
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "Failed to parse workouts.",
            }


async def tp_get_workout(workout_id: str) -> dict[str, Any]:
    """Get full details for a single workout.

    Args:
        workout_id: The workout ID.

    Returns:
        Dict with full workout details including structure.
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

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v6/athletes/{athlete_id}/workouts/{validated.workout_id}"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        if not response.data:
            return {
                "isError": True,
                "error_code": "NOT_FOUND",
                "message": f"Workout {workout_id} not found",
            }

        # Fetch /details endpoint for file infos (not included in main endpoint)
        details_endpoint = f"/fitness/v6/athletes/{athlete_id}/workouts/{validated.workout_id}/details"
        details_response = await client.get(details_endpoint)
        details_raw = (
            details_response.data
            if details_response.success and isinstance(details_response.data, dict)
            else {}
        )

        try:
            raw_data = dict(response.data) if isinstance(response.data, dict) else {}
            structured_workout = _decode_structured_workout(raw_data.get("structure"))
            if structured_workout is not None:
                raw_data["structure"] = structured_workout
            workout = parse_workout_detail(raw_data)

            return {
                "id": str(workout.id),
                "date": workout.date.isoformat(),
                "title": workout.title,
                "sport": workout.sport,
                "workout_type": workout.workout_type,
                "description": workout.description,
                "coach_comments": workout.coach_comments,
                "athlete_comments": workout.athlete_comments,
                "metrics": {
                    "duration_planned": workout.duration_planned,
                    "duration_actual": workout.duration_actual,
                    "tss_planned": workout.tss_planned,
                    "tss_actual": workout.tss_actual,
                    "if_planned": workout.if_planned,
                    "if_actual": workout.if_actual,
                    "distance_planned_km": workout.distance_planned / 1000 if workout.distance_planned else None,
                    "distance_actual_km": workout.distance_actual / 1000 if workout.distance_actual else None,
                    "avg_power": workout.avg_power,
                    "normalized_power": workout.normalized_power,
                    "avg_hr": workout.avg_hr,
                    "avg_cadence": workout.avg_cadence,
                    "elevation_gain": workout.elevation_gain,
                    "calories": workout.calories,
                },
                "completed": workout.completed,
                "structured_workout": structured_workout,
                "device_files": _extract_file_infos(details_raw, "workoutDeviceFileInfos"),
                "attachment_files": _extract_file_infos(details_raw, "attachmentFileInfos"),
            }

        except Exception:
            logger.exception("Failed to parse workout")
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "Failed to parse workout.",
            }


def _km_to_m(km: float) -> float:
    """Convert kilometres to metres."""
    return km * 1000


def _m_to_km(metres: float | None) -> float | None:
    """Convert metres to kilometres, preserving None."""
    return metres / 1000 if metres is not None else None


async def tp_create_workout(
    date_str: str,
    sport: str,
    title: str,
    duration_minutes: int | None = None,
    description: str | None = None,
    distance_km: float | None = None,
    tss_planned: float | None = None,
    structure: dict[str, Any] | str | None = None,
    structured_workout: dict[str, Any] | None = None,
    subtype_id: int | None = None,
    tags: str | None = None,
    feeling: int | None = None,
    rpe: int | None = None,
) -> dict[str, Any]:
    """Create a planned workout.

    Args:
        date_str: Workout date in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).
        sport: Sport type (see SPORT_TYPE_MAP for valid values).
        title: Workout title.
        duration_minutes: Planned duration in minutes (optional if structure provided).
        description: Optional workout description.
        distance_km: Optional planned distance in kilometres.
        tss_planned: Optional planned Training Stress Score.
        structure: Optional interval structure (dict or JSON string).
        structured_workout: Optional native TP structured workout payload.
        subtype_id: Optional workout subtype ID (e.g. Road Bike=3).
        tags: Optional comma-separated tags string.
        feeling: Optional feeling score (0-10).
        rpe: Optional RPE score (1-10).

    Returns:
        Dict with created workout details or error.
    """
    try:
        params = CreateWorkoutInput(
            date=date_str,
            sport=sport,
            title=title,
            duration_minutes=duration_minutes,
            description=description,
            distance_km=distance_km,
            tss_planned=tss_planned,
            structure=structure,
            structured_workout=structured_workout,
            subtype_id=subtype_id,
            tags=tags,
            feeling=feeling,
            rpe=rpe,
        )
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    family_id, type_id = SPORT_TYPE_MAP[params.sport]

    structure_payload = _prepare_structure_payload(params.structure)
    if structure_payload.error is not None:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": structure_payload.error,
        }
    raw_structure_payload, raw_structure_error = _encode_structured_workout(
        params.structured_workout,
    )
    if raw_structure_error is not None:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": raw_structure_error,
        }

    # Use explicit duration if provided, otherwise use structure-computed
    effective_duration: float | None = float(params.duration_minutes) if params.duration_minutes is not None else None
    if effective_duration is None and structure_payload.duration_minutes is not None:
        effective_duration = structure_payload.duration_minutes

    # Use explicit TSS if provided, otherwise use structure-computed
    effective_tss = params.tss_planned
    if effective_tss is None and structure_payload.tss is not None:
        effective_tss = structure_payload.tss

    # Use structure IF if no explicit TSS was given
    effective_if = None
    if params.tss_planned is None and structure_payload.intensity_factor is not None:
        effective_if = structure_payload.intensity_factor

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        payload: dict[str, Any] = {
            "athleteId": athlete_id,
            "workoutDay": _format_workout_day(params.date),
            "workoutTypeFamilyId": family_id,
            "workoutTypeValueId": type_id,
            "title": params.title,
        }
        if isinstance(params.date, datetime_type):
            payload["startTimePlanned"] = _format_start_time_planned(params.date)
        if params.subtype_id is not None:
            payload["workoutSubTypeId"] = params.subtype_id

        if effective_duration is not None:
            payload["totalTimePlanned"] = effective_duration / 60.0

        if params.description:
            payload["description"] = params.description
        if params.distance_km is not None:
            payload["distancePlanned"] = _km_to_m(params.distance_km)
        if effective_tss is not None:
            payload["tssPlanned"] = effective_tss
        if effective_if is not None:
            payload["ifPlanned"] = effective_if
        if structure_payload.wire_structure is not None:
            payload["structure"] = json.dumps(structure_payload.wire_structure)
        elif raw_structure_payload is not None:
            payload["structure"] = raw_structure_payload
        if params.tags is not None:
            payload["tags"] = params.tags
        if params.feeling is not None:
            payload["feeling"] = params.feeling
        if params.rpe is not None:
            payload["rpe"] = params.rpe

        endpoint = f"/fitness/v6/athletes/{athlete_id}/workouts"
        response = await client.post(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        # Type guard: API should return a dict for a single created workout
        if not isinstance(response.data, dict):
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "Unexpected response format from API.",
            }

        return {
            "success": True,
            "workout_id": response.data.get("workoutId"),
            "title": response.data.get("title", title),
            "date": response.data.get("startTimePlanned") or response.data.get("workoutDay", date_str),
            "sport": sport,
        }


async def tp_update_workout(
    workout_id: str,
    sport: str | None = None,
    subtype_id: int | None = None,
    title: str | None = None,
    description: str | None = None,
    date: str | None = None,
    duration_minutes: float | None = None,
    distance_km: float | None = None,
    tss_planned: float | None = None,
    tags: str | None = None,
    athlete_comment: str | None = None,
    coach_comment: str | None = None,
    feeling: int | None = None,
    rpe: int | None = None,
    structure: dict[str, Any] | str | None = None,
    structured_workout: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update fields of an existing workout.

    TP API requires full workout object on PUT - fetches existing, merges, then PUTs.

    Supports either simplified ``structure`` input or a native
    ``structured_workout`` payload, but not both in the same call.

    Returns:
        Dict with updated workout details or error.
    """
    try:
        params = UpdateWorkoutInput(
            workout_id=workout_id,
            sport=sport,
            subtype_id=subtype_id,
            title=title,
            description=description,
            date=date,
            duration_minutes=duration_minutes,
            distance_km=distance_km,
            tss_planned=tss_planned,
            tags=tags,
            athlete_comment=athlete_comment,
            coach_comment=coach_comment,
            feeling=feeling,
            rpe=rpe,
            structure=structure,
            structured_workout=structured_workout,
        )
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    structure_payload = _prepare_structure_payload(params.structure)
    if structure_payload.error is not None:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": structure_payload.error,
        }
    raw_structure_payload, raw_structure_error = _encode_structured_workout(
        params.structured_workout,
    )
    if raw_structure_error is not None:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": raw_structure_error,
        }

    effective_duration = params.duration_minutes
    if effective_duration is None and structure_payload.duration_minutes is not None:
        effective_duration = structure_payload.duration_minutes

    effective_tss = params.tss_planned
    if effective_tss is None and structure_payload.tss is not None:
        effective_tss = structure_payload.tss

    effective_if = None
    if params.structure is not None and params.tss_planned is None and structure_payload.intensity_factor is not None:
        effective_if = structure_payload.intensity_factor

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        # GET existing workout
        get_endpoint = f"/fitness/v6/athletes/{athlete_id}/workouts/{params.workout_id}"
        get_response = await client.get(get_endpoint)

        if get_response.is_error:
            return {
                "isError": True,
                "error_code": get_response.error_code.value if get_response.error_code else "API_ERROR",
                "message": get_response.message,
            }

        if not isinstance(get_response.data, dict):
            return {
                "isError": True,
                "error_code": "NOT_FOUND",
                "message": f"Workout {params.workout_id} not found",
            }

        # Merge updates into existing workout
        existing = get_response.data

        if params.sport is not None:
            family_id, type_id = SPORT_TYPE_MAP[params.sport]
            existing["workoutTypeFamilyId"] = family_id
            existing["workoutTypeValueId"] = type_id
        if params.subtype_id is not None:
            existing["workoutTypeValueId"] = params.subtype_id
        if params.title is not None:
            existing["title"] = params.title
        if params.description is not None:
            existing["description"] = params.description
        if params.date is not None:
            existing["workoutDay"] = _format_workout_day(params.date)
            if isinstance(params.date, datetime_type):
                existing["startTimePlanned"] = _format_start_time_planned(params.date)
            elif existing.get("startTimePlanned"):
                shifted_start = _shift_start_time_planned(existing["startTimePlanned"], params.date)
                if shifted_start is not None:
                    existing["startTimePlanned"] = shifted_start
        if effective_duration is not None:
            existing["totalTimePlanned"] = effective_duration / 60.0
        if params.distance_km is not None:
            existing["distancePlanned"] = _km_to_m(params.distance_km)
        if effective_tss is not None:
            existing["tssPlanned"] = effective_tss
        if params.tags is not None:
            existing["tags"] = params.tags
        if params.athlete_comment is not None:
            existing["athleteComments"] = params.athlete_comment
        if params.coach_comment is not None:
            existing["coachComments"] = params.coach_comment
        if params.feeling is not None:
            existing["feeling"] = params.feeling
        if params.rpe is not None:
            existing["rpe"] = params.rpe
        if params.structure is not None:
            existing["structure"] = json.dumps(structure_payload.wire_structure)
            if effective_if is not None:
                existing["ifPlanned"] = effective_if
            else:
                existing.pop("ifPlanned", None)
        elif raw_structure_payload is not None:
            existing["structure"] = raw_structure_payload

        # PUT updated workout
        put_endpoint = f"/fitness/v6/athletes/{athlete_id}/workouts/{params.workout_id}"
        put_response = await client.put(put_endpoint, json=existing)

        if put_response.is_error:
            return {
                "isError": True,
                "error_code": put_response.error_code.value if put_response.error_code else "API_ERROR",
                "message": put_response.message,
            }

        return {
            "success": True,
            "workout_id": params.workout_id,
            "message": "Workout updated successfully.",
        }


async def tp_delete_workout(workout_id: str) -> dict[str, Any]:
    """Delete a workout.

    Args:
        workout_id: The workout ID.

    Returns:
        Dict with confirmation or error.
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

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v6/athletes/{athlete_id}/workouts/{validated.workout_id}"
        response = await client.delete(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {
            "success": True,
            "message": f"Workout {validated.workout_id} deleted.",
        }


async def tp_copy_workout(
    workout_id: str,
    target_date: str,
    title: str | None = None,
) -> dict[str, Any]:
    """Copy an existing workout to a new date.

    Copies structure, description, coach comments, sport type, subtype,
    duration, distance, TSS. Does not copy completed data or actual metrics.

    Args:
        workout_id: The source workout ID.
        target_date: Target date in ISO format (YYYY-MM-DD).
        title: Optional title override.

    Returns:
        Dict with new workout details or error.
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

    try:
        from datetime import date as date_type

        date_type.fromisoformat(target_date)
    except ValueError:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": f"Invalid target_date: {target_date}",
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        # GET source workout
        get_endpoint = f"/fitness/v6/athletes/{athlete_id}/workouts/{validated.workout_id}"
        get_response = await client.get(get_endpoint)

        if get_response.is_error:
            return {
                "isError": True,
                "error_code": get_response.error_code.value if get_response.error_code else "API_ERROR",
                "message": get_response.message,
            }

        if not isinstance(get_response.data, dict):
            return {
                "isError": True,
                "error_code": "NOT_FOUND",
                "message": f"Workout {validated.workout_id} not found",
            }

        source = get_response.data

        # Build new workout payload - copy planned fields only
        payload: dict[str, Any] = {
            "athleteId": athlete_id,
            "workoutDay": f"{target_date}T00:00:00",
            "workoutTypeFamilyId": source.get("workoutTypeFamilyId"),
            "workoutTypeValueId": source.get("workoutTypeValueId"),
            "title": title or source.get("title", ""),
        }

        # Copy planned fields (not actual/completed data)
        for field in [
            "totalTimePlanned",
            "distancePlanned",
            "tssPlanned",
            "ifPlanned",
            "description",
            "coachComments",
            "tags",
        ]:
            if source.get(field) is not None:
                payload[field] = source[field]

        # Copy structure
        if source.get("structure") is not None:
            structure_val = source["structure"]
            if isinstance(structure_val, dict):
                payload["structure"] = json.dumps(structure_val)
            else:
                payload["structure"] = structure_val

        # POST new workout
        post_endpoint = f"/fitness/v6/athletes/{athlete_id}/workouts"
        post_response = await client.post(post_endpoint, json=payload)

        if post_response.is_error:
            return {
                "isError": True,
                "error_code": post_response.error_code.value if post_response.error_code else "API_ERROR",
                "message": post_response.message,
            }

        if not isinstance(post_response.data, dict):
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "Unexpected response format from API.",
            }

        return {
            "success": True,
            "workout_id": post_response.data.get("workoutId"),
            "title": post_response.data.get("title", payload["title"]),
            "date": target_date,
            "copied_from": validated.workout_id,
        }


async def tp_reorder_workouts(workout_ids: list[int]) -> dict[str, Any]:
    """Reorder workouts on a given day.

    Args:
        workout_ids: List of workout IDs in desired display order.

    Returns:
        Dict with confirmation or error.
    """
    import asyncio

    if not workout_ids:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "workout_ids must not be empty.",
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        async def update_order(wid: int, order: int) -> dict[str, Any] | None:
            get_endpoint = f"/fitness/v6/athletes/{athlete_id}/workouts/{wid}"
            get_response = await client.get(get_endpoint)
            if get_response.is_error or not isinstance(get_response.data, dict):
                return {"workout_id": wid, "error": "Not found"}

            existing = get_response.data
            existing["orderOnDay"] = order

            put_endpoint = f"/fitness/v6/athletes/{athlete_id}/workouts/{wid}"
            put_response = await client.put(put_endpoint, json=existing)
            if put_response.is_error:
                return {"workout_id": wid, "error": put_response.message}
            return None

        tasks = [update_order(wid, idx) for idx, wid in enumerate(workout_ids)]
        results = await asyncio.gather(*tasks)

        errors = [r for r in results if r is not None]
        if errors:
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": f"Some workouts failed to reorder: {errors}",
            }

        return {
            "success": True,
            "message": f"Reordered {len(workout_ids)} workouts.",
        }


async def tp_get_workout_comments(workout_id: str) -> dict[str, Any]:
    """Get comments on a workout.

    Args:
        workout_id: The workout ID.

    Returns:
        Dict with comments list or error.
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

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v2/athletes/{athlete_id}/workouts/{validated.workout_id}/comments"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        if not response.data:
            return {
                "comments": [],
                "count": 0,
                "message": "No comments on this workout.",
            }

        comments = response.data if isinstance(response.data, list) else []
        return {
            "comments": comments,
            "count": len(comments),
        }


async def tp_add_workout_comment(workout_id: str, comment: str) -> dict[str, Any]:
    """Add a comment to a workout.

    Args:
        workout_id: The workout ID.
        comment: The comment text.

    Returns:
        Dict with confirmation or error.
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

    if not comment or not comment.strip():
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "Comment must not be empty.",
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v2/athletes/{athlete_id}/workouts/{validated.workout_id}/comments"
        payload = {"value": comment.strip()}
        response = await client.post(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {
            "success": True,
            "message": "Comment added.",
        }


async def tp_unpair_workout(workout_id: str) -> dict[str, Any]:
    """Unpair (split) a paired workout into separate completed and planned workouts.

    Detaches the completed workout file from the planned workout,
    creating two independent workouts on the same day. No data is lost.

    Args:
        workout_id: The ID of the paired workout to unpair.

    Returns:
        Dict with completed workout(s) and new planned workout info, or error.
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

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = (
            f"/fitness/v6/athletes/{athlete_id}"
            f"/commands/workouts/{validated.workout_id}/split"
        )
        response = await client.post(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        if not isinstance(response.data, dict):
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "Unexpected response format from API.",
            }

        completed = response.data.get("completedWorkouts", [])
        planned = response.data.get("plannedWorkout")

        completed_ids = [w.get("workoutId") for w in completed if isinstance(w, dict)]
        planned_id = planned.get("workoutId") if isinstance(planned, dict) else None

        return {
            "success": True,
            "message": f"Workout {validated.workout_id} unpaired.",
            "completed_workout_ids": completed_ids,
            "planned_workout_id": planned_id,
            "completed_workouts": completed,
            "planned_workout": planned,
        }


async def tp_pair_workout(
    completed_workout_id: str,
    planned_workout_id: str,
) -> dict[str, Any]:
    """Pair (combine) a completed workout with a planned workout.

    Attaches the completed workout data to the planned workout,
    merging them into a single paired workout. All data from both
    workouts is preserved.

    Args:
        completed_workout_id: The ID of the completed (actual) workout.
        planned_workout_id: The ID of the planned workout to pair with.

    Returns:
        Dict with merged workout info, or error.
    """
    try:
        validated_completed = WorkoutIdInput(workout_id=completed_workout_id)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": f"Invalid completed_workout_id: {msg}",
        }

    try:
        validated_planned = WorkoutIdInput(workout_id=planned_workout_id)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": f"Invalid planned_workout_id: {msg}",
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v6/athletes/{athlete_id}/commands/workouts/combine"
        payload = {
            "athleteId": int(athlete_id),
            "completedWorkoutId": int(validated_completed.workout_id),
            "plannedWorkoutId": int(validated_planned.workout_id),
        }
        response = await client.post(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        if not isinstance(response.data, dict):
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "Unexpected response format from API.",
            }

        return {
            "success": True,
            "message": (
                f"Workout {validated_completed.workout_id} paired with "
                f"planned workout {validated_planned.workout_id}."
            ),
            "workout_id": response.data.get("workoutId"),
            "title": response.data.get("title"),
            "workout": response.data,
        }
