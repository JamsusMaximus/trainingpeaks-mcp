"""TOOL-05: tp_get_peaks - Get power or pace peak data."""

from datetime import date, timedelta
from typing import Any, Literal

from tp_mcp.client import TPClient


async def _get_athlete_id(client: TPClient) -> int | None:
    """Get athlete ID from profile."""
    if client.athlete_id:
        return client.athlete_id

    response = await client.get("/users/v3/user")
    if response.success and response.data:
        athlete_id = response.data.get("athleteId")
        client.athlete_id = athlete_id
        return athlete_id
    return None


# Map duration strings to seconds
DURATION_MAP = {
    "5s": 5,
    "10s": 10,
    "30s": 30,
    "1m": 60,
    "2m": 120,
    "5m": 300,
    "10m": 600,
    "20m": 1200,
    "30m": 1800,
    "60m": 3600,
    "90m": 5400,
}


def _seconds_to_duration(seconds: int) -> str:
    """Convert seconds to duration string."""
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h"


async def tp_get_peaks(
    peak_type: Literal["power", "pace"],
    sport: Literal["bike", "run"],
    duration: Literal["5s", "1m", "5m", "20m", "60m", "all"] = "all",
    days: int = 90,
) -> dict[str, Any]:
    """Get power or pace peak data.

    Args:
        peak_type: Type of peak - "power" or "pace".
        sport: Sport type - "bike" or "run".
        duration: Specific duration or "all" for all durations.
        days: Number of days of history to include (default 90).

    Returns:
        Dict with peaks list, sport, peak_type, and days.
    """
    # Validate days
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

        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Build endpoint based on peak type
        if peak_type == "power":
            endpoint = f"/fitness/v3/athletes/{athlete_id}/powerpeaks"
        else:
            endpoint = f"/fitness/v3/athletes/{athlete_id}/pacepeaks"

        params = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
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
                "peaks": [],
                "sport": sport,
                "peak_type": peak_type,
                "days": days,
            }

        try:
            # Parse peaks from response
            # The API returns peaks in various formats, so we normalize here
            peaks_data = response.data if isinstance(response.data, list) else []

            peaks = []
            for peak in peaks_data:
                # Filter by sport if applicable
                peak_sport = peak.get("workoutTypeFamilyId", "").lower()
                if sport == "bike" and "bike" not in peak_sport and "cycling" not in peak_sport:
                    continue
                if sport == "run" and "run" not in peak_sport:
                    continue

                duration_seconds = peak.get("durationSeconds", 0)
                duration_str = _seconds_to_duration(duration_seconds)

                # Filter by requested duration
                if duration != "all" and duration_str != duration:
                    continue

                peaks.append({
                    "duration": duration_str,
                    "duration_seconds": duration_seconds,
                    "value": peak.get("value"),
                    "date": peak.get("activityDate", "").split("T")[0],
                    "activity_id": peak.get("activityId"),
                })

            # Sort by duration
            peaks.sort(key=lambda x: x["duration_seconds"])

            return {
                "peaks": peaks,
                "sport": sport,
                "peak_type": peak_type,
                "days": days,
            }

        except Exception as e:
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": f"Failed to parse peaks: {e}",
            }
