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
    atl_constant: int = 7,
    ctl_constant: int = 42,
) -> dict[str, Any]:
    """Get fitness/fatigue/form data (CTL/ATL/TSB).

    Args:
        days: Days of history to query (default 90)
        atl_constant: ATL decay constant in days (default 7)
        ctl_constant: CTL decay constant in days (default 42)

    Returns:
        Dict with daily CTL, ATL, TSB values and current fitness summary.
    """
    if days < 1 or days > 365:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "days must be between 1 and 365",
        }

    async with TPClient() as client:
        athlete_id = await _get_athlete_id(client)
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        endpoint = f"/fitness/v1/athletes/{athlete_id}/reporting/performancedata/{start_date}/{end_date}"
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
                "days": days,
                "data": [],
                "current": None,
            }

        try:
            data = response.data

            # Format daily data
            daily_data = []
            for entry in data:
                daily_data.append({
                    "date": entry.get("workoutDay", "").split("T")[0],
                    "tss": entry.get("tssActual", 0),
                    "ctl": round(entry.get("ctl", 0), 1),
                    "atl": round(entry.get("atl", 0), 1),
                    "tsb": round(entry.get("tsb", 0), 1),
                })

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
                "days": days,
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
