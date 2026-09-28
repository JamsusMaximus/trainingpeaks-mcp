"""TOOL-03 & TOOL-04: tp_get_workouts and tp_get_workout."""

from datetime import date
from typing import Any, Literal

from tp_mcp.client import TPClient, parse_workout_detail, parse_workout_list
from tp_mcp.tools._helpers import get_athlete_id


async def tp_get_workouts(
    start_date: str,
    end_date: str,
    workout_filter: Literal["all", "planned", "completed"] = "all",
    athlete_id: int | None = None,
) -> dict[str, Any]:
    """Get workouts for a date range.

    Args:
        start_date: Start date in ISO format (YYYY-MM-DD).
        end_date: End date in ISO format (YYYY-MM-DD).
        workout_filter: Filter by status - "all", "planned", or "completed".

    Returns:
        Dict with workouts list, count, and date_range.
    """
    # Validate dates
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError as e:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": f"Invalid date format: {e}. Use YYYY-MM-DD.",
        }

    if start > end:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "start_date must be before or equal to end_date",
        }

    # Limit date range to prevent massive queries
    max_days = 90
    if (end - start).days > max_days:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": f"Date range too large. Max {max_days} days. Use smaller queries.",
        }

    async with TPClient() as client:
        athlete_id = await get_athlete_id(client, athlete_id)
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        # Format dates for API
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")

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

        except Exception as e:
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": f"Failed to parse workouts: {e}",
            }


async def tp_get_workout(workout_id: str, athlete_id: int | None = None) -> dict[str, Any]:
    """Get full details for a single workout.

    Args:
        workout_id: The workout ID.

    Returns:
        Dict with full workout details including structure.
    """
    async with TPClient() as client:
        athlete_id = await get_athlete_id(client, athlete_id)
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v6/athletes/{athlete_id}/workouts/{workout_id}"
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
                    "distance_planned": workout.distance_planned,
                    "distance_actual": workout.distance_actual,
                    "avg_power": workout.avg_power,
                    "normalized_power": workout.normalized_power,
                    "avg_hr": workout.avg_hr,
                    "avg_cadence": workout.avg_cadence,
                    "elevation_gain": workout.elevation_gain,
                    "calories": workout.calories,
                },
                "completed": workout.completed,
            }

        except Exception as e:
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": f"Failed to parse workout: {e}",
            }


# TrainingPeaks workoutTypeValueId per sport
SPORT_TYPE_IDS = {
    "swim": 1,
    "bike": 2,
    "run": 3,
    "strength": 9,
    "other": 100,
}


async def tp_create_workout(
    workout_date: str,
    sport: str,
    title: str,
    description: str | None = None,
    duration_minutes: float | None = None,
    distance_km: float | None = None,
    tss: float | None = None,
    start_time: str | None = None,
    athlete_id: int | None = None,
) -> dict[str, Any]:
    """Create a planned workout on the athlete's calendar.

    Args:
        workout_date: Day in ISO format (YYYY-MM-DD).
        sport: One of SPORT_TYPE_IDS keys.
        title: Workout title.
        description: Workout description shown to the athlete.
        duration_minutes: Planned duration.
        distance_km: Planned distance.
        tss: Planned TSS.
        start_time: Planned start time (HH:MM).

    Returns:
        Dict with the new workout id, date and title.
    """
    try:
        day = date.fromisoformat(workout_date)
    except ValueError as e:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": f"Invalid date format: {e}. Use YYYY-MM-DD.",
        }

    if sport not in SPORT_TYPE_IDS:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": f"Unknown sport '{sport}'. Use one of: {', '.join(SPORT_TYPE_IDS)}.",
        }

    async with TPClient() as client:
        athlete_id = await get_athlete_id(client, athlete_id)
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        day_str = day.isoformat()
        body: dict[str, Any] = {
            "athleteId": athlete_id,
            "workoutDay": f"{day_str}T00:00:00",
            "workoutTypeValueId": SPORT_TYPE_IDS[sport],
            "title": title,
        }
        if description:
            body["description"] = description
        if duration_minutes:
            body["totalTimePlanned"] = duration_minutes / 60
        if distance_km:
            body["distancePlanned"] = distance_km * 1000
        if tss:
            body["tssPlanned"] = tss
        if start_time:
            body["startTimePlanned"] = f"{day_str}T{start_time}:00"

        response = await client.post(f"/fitness/v6/athletes/{athlete_id}/workouts", json=body)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {
            "id": str((response.data or {}).get("workoutId")),
            "date": day_str,
            "title": title,
        }
