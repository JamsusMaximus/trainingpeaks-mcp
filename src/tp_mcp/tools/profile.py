"""TOOL-02: tp_get_profile / tp_list_athletes - Profile and coach tools."""

import logging
from typing import Any

from tp_mcp.client import TPClient

logger = logging.getLogger("tp-mcp")


async def tp_get_profile() -> dict[str, Any]:
    """Get TrainingPeaks athlete profile.

    Returns:
        Dict with athlete_id, name, email, and account_type.
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
