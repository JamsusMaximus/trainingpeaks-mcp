"""TOOL-03, TOOL-04 & TOOL-08: tp_get_workouts, tp_get_workout, tp_create_workout."""

import logging
from typing import Any, Literal

from pydantic import ValidationError

from tp_mcp.client import TPClient, parse_workout_detail, parse_workout_list
from tp_mcp.tools._validation import (
    CreateWorkoutInput,
    DateRangeInput,
    WorkoutIdInput,
    format_validation_error,
)

logger = logging.getLogger("tp-mcp")

# Maps sport name to (workoutTypeFamilyId, workoutTypeValueId)
SPORT_TYPE_MAP: dict[str, tuple[int, int]] = {
    "Swim": (1, 1),
    "Bike": (2, 2),
    "Run": (3, 3),
    "Brick": (4, 4),
    "Crosstrain": (5, 5),
    "Walk": (6, 6),
    "Strength": (7, 7),
    "Rowing": (8, 8),
    "XCSki": (9, 9),
    "Other": (10, 10),
    "Custom": (11, 11),
    "DayOff": (12, 12),
    "MtnBike": (13, 13),
}


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

        try:
            workout = parse_workout_detail(response.data)

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
            }

        except Exception:
            logger.exception("Failed to parse workout")
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "Failed to parse workout.",
            }


async def tp_create_workout(
    date_str: str,
    sport: str,
    title: str,
    duration_minutes: int,
    description: str | None = None,
    distance_km: float | None = None,
    tss_planned: float | None = None,
) -> dict[str, Any]:
    """Create a planned workout.

    Args:
        date_str: Workout date in ISO format (YYYY-MM-DD).
        sport: Sport type (see SPORT_TYPE_MAP for valid values).
        title: Workout title.
        duration_minutes: Planned duration in minutes.
        description: Optional workout description.
        distance_km: Optional planned distance in kilometres.
        tss_planned: Optional planned Training Stress Score.

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
        )
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    family_id, type_id = SPORT_TYPE_MAP[params.sport]

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
            "workoutDay": f"{params.date.isoformat()}T00:00:00",
            "workoutTypeFamilyId": family_id,
            "workoutTypeValueId": type_id,
            "title": params.title,
            "totalTimePlanned": params.duration_minutes / 60.0,
        }
        if params.description:
            payload["description"] = params.description
        if params.distance_km is not None:
            payload["distancePlanned"] = params.distance_km * 1000  # API expects metres
        if params.tss_planned is not None:
            payload["tssPlanned"] = params.tss_planned

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
            "date": response.data.get("workoutDay", date_str),
            "sport": sport,
        }
