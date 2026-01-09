"""TOOL-02: tp_get_profile - Get athlete profile and ID."""

from typing import Any

from tp_mcp.client import TPClient


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
        except Exception as e:
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": f"Failed to parse profile: {e}",
            }
