"""Shared helpers for TrainingPeaks MCP tools."""

from tp_mcp.client import TPClient


async def get_athlete_id(client: TPClient, athlete_id: int | None = None) -> int | None:
    """Get athlete ID, using override if provided or auto-detecting from profile.

    Args:
        client: TPClient instance.
        athlete_id: Optional explicit athlete ID (for coach accounts).

    Returns:
        Athlete ID or None if not found.
    """
    if athlete_id:
        return athlete_id

    if client.athlete_id:
        return client.athlete_id

    response = await client.get("/users/v3/user")
    if response.success and response.data:
        # API returns nested structure: { user: { ... } }
        user_data = response.data.get("user", response.data)

        # Try personId first, then athletes array
        aid = user_data.get("personId")
        if not aid:
            athletes = user_data.get("athletes", [])
            if athletes:
                aid = athletes[0].get("athleteId")

        client.athlete_id = aid
        return aid
    return None
