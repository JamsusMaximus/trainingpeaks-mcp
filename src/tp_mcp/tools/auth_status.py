"""TOOL-01: tp_auth_status - Check authentication status."""

from typing import Any

from tp_mcp.auth import AuthStatus, get_credential, get_storage_backend, validate_auth


async def tp_auth_status() -> dict[str, Any]:
    """Check TrainingPeaks authentication status.

    Returns:
        Dict with auth status, athlete_id if valid, and any action needed.
    """
    cred = get_credential()

    if not cred.success or not cred.cookie:
        return {
            "valid": False,
            "athlete_id": None,
            "message": "No credential stored",
            "action_needed": "Run 'tp-mcp auth' to authenticate",
        }

    result = await validate_auth(cred.cookie)

    if result.is_valid:
        return {
            "valid": True,
            "athlete_id": result.athlete_id,
            "email": result.email,
            "storage": get_storage_backend(),
            "message": "Authentication valid",
            "action_needed": None,
        }

    action_map = {
        AuthStatus.EXPIRED: "Session expired. Run 'tp-mcp auth' to re-authenticate.",
        AuthStatus.INVALID: "Invalid credentials. Run 'tp-mcp auth' to re-authenticate.",
        AuthStatus.NETWORK_ERROR: "Network error. Check connection and retry.",
    }

    return {
        "valid": False,
        "athlete_id": None,
        "message": result.message,
        "action_needed": action_map.get(result.status, "Run 'tp-mcp auth' to authenticate"),
    }
