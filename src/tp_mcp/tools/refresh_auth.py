"""TOOL-08: tp_refresh_auth - Attempt to refresh authentication from browser.

SECURITY NOTES:
- Cookie values are NEVER included in the return dict (would leak to Claude)
- Only returns: success status, browser name, athlete_id, email
- Cookie is stored directly via store_credential(), never passed through return
"""

from typing import Any

from tp_mcp.auth import store_credential, validate_auth
from tp_mcp.auth.browser import extract_tp_cookie


def _sanitize_result(result: dict[str, Any]) -> dict[str, Any]:
    """SECURITY: Ensure no cookie values in result dict before returning to Claude.

    This is a defense-in-depth measure. Cookie values should never be added
    to the result dict in the first place, but this ensures they can't leak
    even if a future code change accidentally adds one.
    """
    # List of keys that could contain sensitive data
    sensitive_keys = ["cookie", "token", "auth", "credential", "password", "secret"]
    sanitized = {}
    for key, value in result.items():
        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in sensitive_keys):
            continue  # Skip sensitive keys entirely
        sanitized[key] = value
    return sanitized


async def tp_refresh_auth(browser: str = "auto") -> dict[str, Any]:
    """Attempt to refresh TrainingPeaks authentication by extracting cookie from browser.

    This tool tries to automatically extract a fresh cookie from the user's browser.
    Requires the user to be logged into TrainingPeaks in their browser.

    Args:
        browser: Browser to extract from. Options: chrome, firefox, safari, edge, auto.
                 Use 'auto' to try all browsers.

    Returns:
        Dict with success status and message.
    """
    # Try to extract cookie from browser
    result = extract_tp_cookie(browser if browser != "auto" else None)

    if not result.success:
        # Check if it's a missing dependency issue
        if "not installed" in result.message:
            return {
                "success": False,
                "message": "Browser extraction not available",
                "details": "The browser-cookie3 package is not installed.",
                "action_needed": "Run: pip install tp-mcp[browser]",
            }

        return {
            "success": False,
            "message": "Could not extract cookie from browser",
            "details": result.message,
            "action_needed": "Make sure you're logged into TrainingPeaks at app.trainingpeaks.com in your browser, then try again. Or run 'tp-mcp auth' manually.",
        }

    # Validate the extracted cookie
    cookie = result.cookie
    validation = await validate_auth(cookie)

    if not validation.is_valid:
        return {
            "success": False,
            "message": "Extracted cookie is invalid or expired",
            "details": validation.message,
            "action_needed": "Log into TrainingPeaks at app.trainingpeaks.com in your browser, then try again.",
        }

    # Store the valid cookie
    store_result = store_credential(cookie)

    if not store_result.success:
        return {
            "success": False,
            "message": "Could not store the refreshed cookie",
            "details": store_result.message,
            "action_needed": "Run 'tp-mcp auth' manually.",
        }

    # SECURITY: Sanitize before returning to ensure no cookie leakage
    return _sanitize_result({
        "success": True,
        "message": f"Authentication refreshed from {result.browser}",
        "athlete_id": validation.athlete_id,
        "email": validation.email,
        "action_needed": None,
    })
