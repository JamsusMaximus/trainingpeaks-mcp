"""TOOL-05: tp_get_peaks - Get personal records by sport and type."""

import logging
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import ValidationError

from tp_mcp.client import TPClient
from tp_mcp.tools._validation import PeaksInput, WorkoutIdInput, format_validation_error

logger = logging.getLogger("tp-mcp")

# Valid PR types by sport
BIKE_PR_TYPES = [
    "power5sec",
    "power1min",
    "power5min",
    "power10min",
    "power20min",
    "power60min",
    "power90min",
    "hR5sec",
    "hR1min",
    "hR5min",
    "hR10min",
    "hR20min",
    "hR60min",
    "hR90min",
]

RUN_PR_TYPES = [
    "hR5sec",
    "hR1min",
    "hR5min",
    "hR10min",
    "hR20min",
    "hR60min",
    "hR90min",
    "speed400Meter",
    "speed800Meter",
    "speed1K",
    "speed1Mi",
    "speed5K",
    "speed5Mi",
    "speed10K",
    "speed10Mi",
    "speedHalfMarathon",
    "speedMarathon",
    "speed50K",
]


async def tp_get_peaks(
    sport: Literal["Bike", "Run"],
    pr_type: str,
    days: int = 3650,
) -> dict[str, Any]:
    """Get personal records (peaks) for a sport and PR type.

    Args:
        sport: Sport type - "Bike" or "Run"
        pr_type: PR type - e.g., "power5sec", "power20min", "speed5K"
        days: Days of history to query (default 3650 = ~10 years for all-time)

    Returns:
        Dict with ranked list of personal records.
    """
    try:
        validated = PeaksInput(sport=sport, pr_type=pr_type, days=days)
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

        end_date = date.today()
        start_date = end_date - timedelta(days=validated.days)

        endpoint = f"/personalrecord/v2/athletes/{athlete_id}/{sport}"
        params = {
            "prType": pr_type,
            "startDate": f"{start_date}T00:00:00",
            "endDate": f"{end_date}T00:00:00",
        }

        response = await client.get(endpoint, params=params)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        if not response.data:
            return {
                "sport": sport,
                "pr_type": pr_type,
                "days": days,
                "records": [],
            }

        try:
            records = []
            for record in response.data:
                records.append(
                    {
                        "rank": record.get("rank"),
                        "value": record.get("value"),
                        "workout_id": record.get("workoutId"),
                        "workout_title": record.get("workoutTitle"),
                        "date": record.get("workoutDate", "").split("T")[0],
                    }
                )

            return {
                "sport": sport,
                "pr_type": pr_type,
                "days": days,
                "records": records,
            }

        except Exception:
            logger.exception("Failed to parse personal records")
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "Failed to parse personal records.",
            }


async def tp_get_workout_prs(workout_id: str) -> dict[str, Any]:
    """Get personal records set during a specific workout.

    Args:
        workout_id: The workout ID to get PRs for.

    Returns:
        Dict with personal records from that workout.
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

        endpoint = f"/personalrecord/v2/athletes/{athlete_id}/workouts/{validated.workout_id}"
        params = {"displayPeaksForBasic": "true"}

        response = await client.get(endpoint, params=params)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        if not response.data:
            return {
                "workout_id": workout_id,
                "personal_record_count": 0,
                "records": [],
            }

        try:
            data = response.data
            records = data.get("personalRecords", [])

            power_records = []
            hr_records = []
            speed_records = []

            for record in records:
                pr_class = record.get("class", "")
                timeframe = record.get("timeFrame", {})

                formatted = {
                    "type": record.get("type"),
                    "value": record.get("value"),
                    "rank": record.get("rank"),
                    "timeframe": timeframe.get("name", ""),
                }

                if pr_class == "Power":
                    power_records.append(formatted)
                elif pr_class == "HeartRate":
                    hr_records.append(formatted)
                elif pr_class == "Speed":
                    speed_records.append(formatted)

            return {
                "workout_id": workout_id,
                "personal_record_count": data.get("personalRecordCount", len(records)),
                "power_records": power_records if power_records else None,
                "heart_rate_records": hr_records if hr_records else None,
                "speed_records": speed_records if speed_records else None,
            }

        except Exception:
            logger.exception("Failed to parse personal records")
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "Failed to parse personal records.",
            }
