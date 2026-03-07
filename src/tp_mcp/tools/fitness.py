"""TOOL-06: tp_get_fitness - Get CTL/ATL/TSB fitness data."""

from datetime import date, timedelta
from typing import Any

from tp_mcp.client import TPClient


async def _get_athlete_id(client: TPClient) -> int | None:
    """Get athlete ID from profile."""
    if client.athlete_id:
        return client.athlete_id

    response = await client.get("/users/v3/user")
    if response.success and response.data:
        user_data = response.data.get("user", response.data)
        athlete_id = user_data.get("personId")
        if not athlete_id:
            athletes = user_data.get("athletes", [])
            if athletes:
                athlete_id = athletes[0].get("athleteId")
        client.athlete_id = athlete_id
        return athlete_id
    return None


async def tp_get_fitness(
    days: int = 90,
    start_date: str | None = None,
    end_date: str | None = None,
    atl_constant: int = 7,
    ctl_constant: int = 42,
) -> dict[str, Any]:
    """Get fitness/fatigue/form data (CTL/ATL/TSB).

    Args:
        days: Days of history (default 90). Ignored if start_date/end_date provided.
        start_date: Optional start date (YYYY-MM-DD) for historical queries.
        end_date: Optional end date (YYYY-MM-DD) for historical queries.
        atl_constant: ATL decay constant in days (default 7)
        ctl_constant: CTL decay constant in days (default 42)

    Returns:
        Dict with daily CTL, ATL, TSB values and current fitness summary.
    """
    # Parse dates if provided, otherwise use days from today
    try:
        if start_date and end_date:
            query_start = date.fromisoformat(start_date)
            query_end = date.fromisoformat(end_date)
            if query_start > query_end:
                return {
                    "isError": True,
                    "error_code": "VALIDATION_ERROR",
                    "message": "start_date must be before end_date",
                }
            query_days = (query_end - query_start).days
        else:
            if days < 1 or days > 365:
                return {
                    "isError": True,
                    "error_code": "VALIDATION_ERROR",
                    "message": "days must be between 1 and 365",
                }
            query_end = date.today()
            query_start = query_end - timedelta(days=days)
            query_days = days
    except ValueError as e:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": f"Invalid date format. Use YYYY-MM-DD. Error: {e}",
        }

    async with TPClient() as client:
        athlete_id = await _get_athlete_id(client)
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        base = f"/fitness/v1/athletes/{athlete_id}/reporting/performancedata"
        endpoint = f"{base}/{query_start}/{query_end}"
        body = {
            "atlConstant": atl_constant,
            "atlStart": 0,
            "ctlConstant": ctl_constant,
            "ctlStart": 0,
            "workoutTypes": [],
        }

        response = await client.post(endpoint, json=body)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        if not response.data:
            return {
                "start_date": str(query_start),
                "end_date": str(query_end),
                "days": query_days,
                "data": [],
                "current": None,
            }

        try:
            data = response.data

            # Format daily data
            daily_data = []
            for entry in data:
                daily_data.append(
                    {
                        "date": entry.get("workoutDay", "").split("T")[0],
                        "tss": entry.get("tssActual", 0),
                        "ctl": round(entry.get("ctl", 0), 1),
                        "atl": round(entry.get("atl", 0), 1),
                        "tsb": round(entry.get("tsb", 0), 1),
                    }
                )

            # Get current (latest) values
            current = None
            if daily_data:
                latest = daily_data[-1]
                current = {
                    "ctl": latest["ctl"],
                    "atl": latest["atl"],
                    "tsb": latest["tsb"],
                    "fitness_status": _get_fitness_status(latest["tsb"]),
                }

            return {
                "start_date": str(query_start),
                "end_date": str(query_end),
                "days": query_days,
                "current": current,
                "daily_data": daily_data,
            }

        except Exception as e:
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": f"Failed to parse fitness data: {e}",
            }


def _get_fitness_status(tsb: float) -> str:
    """Get human-readable fitness status from TSB."""
    if tsb > 25:
        return "Very Fresh (detraining risk)"
    elif tsb > 10:
        return "Fresh (race ready)"
    elif tsb > 0:
        return "Neutral (normal training)"
    elif tsb > -10:
        return "Tired (absorbing training)"
    elif tsb > -25:
        return "Very Tired (high fatigue)"
    else:
        return "Exhausted (overreaching risk)"
