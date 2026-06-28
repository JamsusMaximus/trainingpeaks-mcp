"""TOOL-02: tp_get_profile / tp_list_athletes - Profile and coach tools."""

import logging
from datetime import datetime, timezone
from typing import Any

from tp_mcp.client import TPClient
from tp_mcp.client.context import athlete_override

logger = logging.getLogger("tp-mcp")


def _account_fields(entry: dict[str, Any]) -> dict[str, Any]:
    """Surface raw premium/account fields from a coach-roster ``athletes[]``
    entry — passthrough, NOT interpreted.

    /users/v3/user does NOT expose a clean ``isPremium`` for a coached athlete
    (it belongs to the logged-in user). What it DOES carry on each roster entry
    are several account-related fields whose exact semantics aren't documented
    by TP — we hand them all through so callers can compare them across known
    paid / coach-paid / free / trial athletes and learn the pattern. ``expired``
    is the only derived bit: True when ``expireOn`` is in the past.

    Known fields per entry (live-verified on a coach account):
      • ``expireOn`` — ISO timestamp; some kind of expiration (likely premium /
        coach-pairing). Many active athletes show past dates → semantics unclear.
      • ``athleteType`` (int) / ``userType`` (int) — tier-ish codes, values vary
        (0/2/4/5 and 1/4/6 in our sample).
      • ``premiumTrial`` / ``premiumTrialDaysRemaining`` — trial state.
      • ``downgradeAllowed`` / ``downgradeAllowedOn`` / ``lastUpgradeOn`` —
        billing-action hints.
    """
    exp_raw = entry.get("expireOn")
    expired: bool | None = None
    if isinstance(exp_raw, str) and exp_raw:
        try:
            dt = datetime.fromisoformat(exp_raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            expired = dt < datetime.now(timezone.utc)
        except ValueError:
            expired = None
    return {
        "expire_on": exp_raw,
        "expired": expired,
        "athlete_type": entry.get("athleteType"),
        "user_type": entry.get("userType"),
        "premium_trial": entry.get("premiumTrial"),
        "premium_trial_days_remaining": entry.get("premiumTrialDaysRemaining"),
        "downgrade_allowed": entry.get("downgradeAllowed"),
        "downgrade_allowed_on": entry.get("downgradeAllowedOn"),
        "last_upgrade_on": entry.get("lastUpgradeOn"),
    }


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
        # A clean «premium / basic» label isn't exposed for a coached athlete by
        # /users/v3/user. Raw account-related fields ARE present on the roster
        # entry, surfaced under `account` for caller-side analysis (see
        # _account_fields docstring for the known shape and caveats).
        "account_type": None,
        "account": _account_fields(entry),
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

    Each entry carries ``athlete_id``, ``name``, ``is_self`` plus an ``account``
    sub-dict with RAW premium / account fields from the coach roster
    (``expire_on``, ``expired``, ``athlete_type``, ``user_type``,
    ``premium_trial[_days_remaining]``, ``downgrade_allowed[_on]``,
    ``last_upgrade_on``). Exact semantics aren't documented by TP — surfaced
    passthrough so callers can correlate them against known coach-paid vs
    self-paid vs free athletes. See ``_account_fields`` for the field catalogue
    and caveats.
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
                "account": _account_fields(a),
            })

        return {"athletes": result}
