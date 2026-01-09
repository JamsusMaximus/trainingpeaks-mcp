"""TOOL-02: tp_get_profile - Get athlete profile and ID."""

from typing import Any

from tp_mcp.client import TPClient, parse_user_profile


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
            profile = parse_user_profile(response.data)
            return {
                "athlete_id": profile.athlete_id,
                "name": profile.name,
                "email": profile.email,
                "account_type": profile.account_type,
            }
        except Exception as e:
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": f"Failed to parse profile: {e}",
            }
