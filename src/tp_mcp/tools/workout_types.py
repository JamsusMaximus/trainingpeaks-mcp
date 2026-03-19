"""Workout types catalogue tool."""

import logging
from typing import Any

from tp_mcp.client import TPClient

logger = logging.getLogger("tp-mcp")


async def tp_get_workout_types() -> dict[str, Any]:
    """List all sport types and their subtypes with IDs.

    Returns:
        Dict with hierarchical type/subtype structure.
    """
    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = "/fitness/v6/workouttypes"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        if not response.data or not isinstance(response.data, list):
            return {"workout_types": [], "count": 0}

        types: list[dict[str, Any]] = []
        for wt in response.data:
            entry: dict[str, Any] = {
                "id": wt.get("id", wt.get("workoutTypeId")),
                "name": wt.get("name", wt.get("description", "")),
            }
            subtypes = wt.get("subTypes", wt.get("children", []))
            if subtypes:
                entry["subtypes"] = [
                    {
                        "id": st.get("workoutTypeId", st.get("id")),
                        "name": st.get("description", st.get("name", "")),
                    }
                    for st in subtypes
                ]
            types.append(entry)

        return {"workout_types": types, "count": len(types)}
