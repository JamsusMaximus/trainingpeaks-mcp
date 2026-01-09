"""TOOL-03 & TOOL-04: tp_get_workouts and tp_get_workout."""

from datetime import date
from typing import Any, Literal

from tp_mcp.client import TPClient, parse_workout_detail, parse_workout_list


async def _get_athlete_id(client: TPClient) -> int | None:
    """Get athlete ID from profile."""
    if client.athlete_id:
        return client.athlete_id

    response = await client.get("/users/v3/user")
    if response.success and response.data:
        # API returns nested structure: { user: { ... } }
        user_data = response.data.get("user", response.data)

        # Try personId first, then athletes array
        athlete_id = user_data.get("personId")
        if not athlete_id:
            athletes = user_data.get("athletes", [])
            if athletes:
                athlete_id = athletes[0].get("athleteId")

        client.athlete_id = athlete_id
        return athlete_id
    return None


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
        athlete_id = await _get_athlete_id(client)
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


async def tp_get_workout(workout_id: str) -> dict[str, Any]:
    """Get full details for a single workout.

    Args:
        workout_id: The workout ID.

    Returns:
        Dict with full workout details including structure.
    """
    async with TPClient() as client:
        athlete_id = await _get_athlete_id(client)
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
