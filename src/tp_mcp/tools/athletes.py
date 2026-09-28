"""TOOL: tp_get_athletes - List athletes for coach accounts."""

from typing import Any

from tp_mcp.client import TPClient


async def tp_get_athletes() -> dict[str, Any]:
    """List all athletes accessible to the authenticated user.

    For coach accounts, returns all athletes under the coach.
    For individual accounts, returns a single-item list with the user's own athlete ID.

    Returns:
        Dict with athletes list containing athlete_id and name for each.
    """
    async with TPClient() as client:
        response = await client.get("/users/v3/user")

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        if not response.data:
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "Empty response from API",
            }

        try:
            user_data = response.data.get("user", response.data)
            athletes_raw = user_data.get("athletes", [])

            athletes = []
            for a in athletes_raw:
                first = a.get("firstName", "")
                last = a.get("lastName", "")
                name = f"{first} {last}".strip() or None
                athletes.append({
                    "athlete_id": a.get("athleteId"),
                    "name": name,
                })

            # If no athletes array, fall back to personId (individual account)
            if not athletes:
                person_id = user_data.get("personId")
                if person_id:
                    first = user_data.get("firstName", "")
                    last = user_data.get("lastName", "")
                    name = user_data.get("fullName") or f"{first} {last}".strip() or None
                    athletes.append({
                        "athlete_id": person_id,
                        "name": name,
                    })

            return {
                "athletes": athletes,
                "count": len(athletes),
            }

        except Exception as e:
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": f"Failed to parse athletes: {e}",
            }
