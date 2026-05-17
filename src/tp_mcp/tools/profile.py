"""TOOL-02: tp_get_profile / tp_list_athletes - Profile and coach tools."""

import logging
from typing import Any

from tp_mcp.client import TPClient
from tp_mcp.client.context import athlete_override

logger = logging.getLogger("tp-mcp")


async def _targeted_athlete_profile(client: TPClient) -> dict[str, Any]:
    """Build a profile for a coach's targeted roster athlete.

    /users/v3/user only ever describes the logged-in user, so a targeted
    athlete's profile is assembled from their entry in the coach's roster.
    """
    athlete_id = await client.ensure_athlete_id()
    if not athlete_id:
        return {
            "isError": True,
            "error_code": "NOT_FOUND",
            "message": "Could not resolve that athlete. Check the name or ID against tp_list_athletes.",
        }

    user_data = await client._get_user_data()
    athletes = user_data.get("athletes", []) if user_data else []
    entry = next((a for a in athletes if a.get("athleteId") == athlete_id), None)
    if entry is None:
        return {
            "isError": True,
            "error_code": "NOT_FOUND",
            "message": "That athlete is not in your roster.",
        }

    first = entry.get("firstName", "")
    last = entry.get("lastName", "")
    return {
        "athlete_id": athlete_id,
        "name": f"{first} {last}".strip(),
        "email": entry.get("email"),
        # Premium status belongs to the logged-in account, not a coached
        # athlete, so it is not available when targeting one.
        "account_type": None,
    }


async def tp_get_profile() -> dict[str, Any]:
    """Get TrainingPeaks athlete profile.

    On a coach account, pass `athlete` to get a roster athlete's profile
    instead of your own.

    Returns:
        Dict with athlete_id, name, email, and account_type. account_type
        is null when targeting a coached athlete.
    """
    async with TPClient() as client:
        # Coach targeting a specific athlete: resolve via the roster (#68).
        if athlete_override.get() is not None:
            return await _targeted_athlete_profile(client)

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
            # API returns nested structure: { user: { ... } }
            user_data = response.data.get("user", response.data)

            # Get athlete ID from athletes array or personId
            athlete_id = user_data.get("personId")
            if not athlete_id:
                athletes = user_data.get("athletes", [])
                if athletes:
                    athlete_id = athletes[0].get("athleteId")

            # Check if premium
            is_premium = user_data.get("settings", {}).get("account", {}).get("isPremium", False)
            account_type = "premium" if is_premium else "basic"

            first = user_data.get("firstName", "")
            last = user_data.get("lastName", "")
            name = user_data.get("fullName") or f"{first} {last}".strip()

            return {
                "athlete_id": athlete_id,
                "name": name,
                "email": user_data.get("email"),
                "account_type": account_type,
            }
        except Exception:
            logger.exception("Failed to parse profile")
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "Failed to parse profile.",
            }


async def tp_list_athletes() -> dict[str, Any]:
    """List athletes available to this account (coach accounts).

    Returns:
        Dict with athletes list, each containing athlete_id, name, and is_self flag.
    """
    async with TPClient() as client:
        user_data = await client._get_user_data()

        if not user_data:
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "Could not retrieve user data.",
            }

        person_id = user_data.get("personId")
        coach_email = (user_data.get("email") or "").lower()
        athletes = user_data.get("athletes", [])

        if not athletes:
            return {
                "athletes": [],
                "message": "No athletes found. This may not be a coach account.",
            }

        result = []
        for a in athletes:
            first = a.get("firstName", "")
            last = a.get("lastName", "")
            athlete_email = (a.get("email") or "").lower()
            is_self = (
                a.get("coachedBy") == person_id
                and athlete_email == coach_email
            )
            result.append({
                "athlete_id": a.get("athleteId"),
                "name": f"{first} {last}".strip(),
                "is_self": is_self,
            })

        return {"athletes": result}
