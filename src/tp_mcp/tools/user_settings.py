"""Account and notification settings: the calendar layout, compliance colouring, landing page and alerts.

Verified against the live API (read, and a no-change Save in the web app to capture the writes):
  • read   → GET /users/v1/user/{id}/settings  (sections: calendar, workout, general, metrics, atp, ...)
  • write  → PUT /users/v1/user/{id}/settings/{section}  for calendar, workout, general and metrics
             (the web app PUTs the whole section; 200/204)
  • notify → GET/PUT /notification/v1/coachSettings  (a list, one entry per athlete, each with per-type details)
             GET /notification/v1/athletes/{id}/settings  (the athlete's own)
`{id}` is the coach/user id for the account dialog, and the athlete id for that athlete's own settings; the web
calendar reads the athlete's document, so the compliance tools use that one.
"""

import copy
import logging
from typing import Any

from tp_mcp.client import TPClient

logger = logging.getLogger("tp-mcp")

# Sections the web app saves with PUT /settings/{section}; others are read-only here.
WRITABLE_SECTIONS = ("calendar", "workout", "general", "metrics")
_SCOPES = ("athlete", "account")
_NOTIFY_TYPES = (
    "WorkoutUpload",
    "WorkoutComment",
    "WorkoutCompleted",
    "ThresholdChange",
    "CalendarNoteCreated",
    "AvailabilityCreated",
)


def _err(code: str, message: str) -> dict[str, Any]:
    return {"isError": True, "error_code": code, "message": message}


def _api_err(response: Any) -> dict[str, Any]:
    return _err(response.error_code.value if response.error_code else "API_ERROR", response.message)


async def _settings_owner(client: TPClient, scope: str) -> tuple[int | None, dict[str, Any] | None]:
    """The id whose settings document to use: the targeted athlete, or the signed-in user's account."""
    if scope not in _SCOPES:
        return None, _err("VALIDATION_ERROR", f"scope must be one of {list(_SCOPES)}.")
    if scope == "athlete":
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return None, _err("AUTH_INVALID", "Could not get athlete ID. Re-authenticate.")
        return athlete_id, None
    ud = await client._get_user_data()
    uid = (ud or {}).get("userId") or (ud or {}).get("personId")
    if not isinstance(uid, int):
        return None, _err("AUTH_INVALID", "Could not get user ID. Re-authenticate.")
    return uid, None


async def tp_get_user_settings(section: str | None = None, scope: str = "athlete") -> dict[str, Any]:
    """Get calendar / layout / general settings.

    Args:
        section: One section (calendar, workout, general, metrics, atp, dashboard, privacy, ...) or omit for all.
        scope: "athlete" (the targeted athlete's own settings, what their calendar uses) or "account"
            (the signed-in coach/user account).

    Returns:
        Dict with the settings document (or the one section) and the owner id.
    """
    async with TPClient() as client:
        owner, err = await _settings_owner(client, scope)
        if err:
            return err
        response = await client.get(f"/users/v1/user/{owner}/settings")
        if response.is_error:
            return _api_err(response)
        doc = response.data if isinstance(response.data, dict) else {}
        if section is None:
            return {"scope": scope, "owner_id": owner, "writable_sections": list(WRITABLE_SECTIONS), "settings": doc}
        if section not in doc:
            return _err("VALIDATION_ERROR", f"Unknown section '{section}'. Available: {sorted(doc)}.")
        return {"scope": scope, "owner_id": owner, "section": section, "settings": doc[section]}


def _merge(base: Any, changes: Any) -> Any:
    """Deep-merge dicts; anything else (lists, scalars) is replaced."""
    if isinstance(base, dict) and isinstance(changes, dict):
        merged = copy.deepcopy(base)
        for k, v in changes.items():
            merged[k] = _merge(base.get(k), v) if k in base else copy.deepcopy(v)
        return merged
    return copy.deepcopy(changes)


async def tp_update_user_settings(
    section: str,
    changes: dict[str, Any] | list[Any],
    scope: str = "athlete",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Change calendar / layout / general settings. Fetches the section, merges `changes`, saves it back.

    Args:
        section: calendar, workout, general or metrics.
        changes: Fields to change. Objects are merged key by key; lists (and the `metrics` section, which is a
            list) replace the existing value entirely, so send the complete list.
        scope: "athlete" or "account" (see tp_get_user_settings).
        dry_run: Show the before/after without saving.

    Returns:
        Dict with `previous` (the section as it was, so it can be put back) and `updated`.
    """
    if section not in WRITABLE_SECTIONS:
        return _err("VALIDATION_ERROR", f"section must be one of {list(WRITABLE_SECTIONS)}.")
    if not changes:
        return _err("VALIDATION_ERROR", "changes is required.")
    async with TPClient() as client:
        owner, err = await _settings_owner(client, scope)
        if err:
            return err
        response = await client.get(f"/users/v1/user/{owner}/settings")
        if response.is_error:
            return _api_err(response)
        doc = response.data if isinstance(response.data, dict) else {}
        if section not in doc:
            return _err("NOT_FOUND", f"Section '{section}' not found in the settings.")
        previous = doc[section]
        if isinstance(previous, list) != isinstance(changes, list):
            kind = "a list" if isinstance(previous, list) else "an object"
            return _err("VALIDATION_ERROR", f"The '{section}' section is {kind}; changes must be {kind} too.")
        updated = _merge(previous, changes)
        result: dict[str, Any] = {"scope": scope, "owner_id": owner, "section": section,
                                  "previous": previous, "updated": updated}
        if dry_run:
            return {**result, "dry_run": True}
        put = await client.put(f"/users/v1/user/{owner}/settings/{section}", json=updated)
        if put.is_error:
            return _api_err(put)
        return result


async def tp_get_notification_settings() -> dict[str, Any]:
    """Get notification settings: the coach's per-athlete alerts, and the targeted athlete's own.

    Returns:
        Dict with `coach` (list per athlete; each has in-app/mobile/email switches and per-type `details`)
        and `athlete`.
    """
    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return _err("AUTH_INVALID", "Could not get athlete ID. Re-authenticate.")
        coach = await client.get("/notification/v1/coachSettings")
        own = await client.get(f"/notification/v1/athletes/{athlete_id}/settings")
        if own.is_error:
            return _api_err(own)
        return {
            "athlete_id": athlete_id,
            "athlete": own.data,
            "coach": None if coach.is_error else coach.data,
            "types": list(_NOTIFY_TYPES),
        }


async def tp_update_notification_settings(
    athlete_id: int,
    type: str | None = None,
    in_app: bool | None = None,
    mobile: bool | None = None,
    email: bool | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Change the coach's alerts for one athlete. Sets the athlete-wide switches, or one notification type.

    Args:
        athlete_id: The athlete (from tp_get_notification_settings).
        type: One of WorkoutUpload, WorkoutComment, WorkoutCompleted, ThresholdChange, CalendarNoteCreated,
            AvailabilityCreated. Omit to change the athlete-wide switches.
        in_app / mobile / email: New values; leave out to keep.
        dry_run: Show the before/after without saving.

    Returns:
        Dict with `previous` and `updated` entries for that athlete.
    """
    if type is not None and type not in _NOTIFY_TYPES:
        return _err("VALIDATION_ERROR", f"type must be one of {list(_NOTIFY_TYPES)}.")
    values = {"inAppEnabled": in_app, "mobileEnabled": mobile, "emailEnabled": email}
    values = {k: v for k, v in values.items() if v is not None}
    if not values:
        return _err("VALIDATION_ERROR", "Set at least one of in_app, mobile, email.")
    async with TPClient() as client:
        response = await client.get("/notification/v1/coachSettings")
        if response.is_error:
            return _api_err(response)
        entries = response.data if isinstance(response.data, list) else []
        entry = next((e for e in entries if e.get("athleteId") == athlete_id), None)
        if entry is None:
            return _err("NOT_FOUND", f"No notification settings for athlete {athlete_id}.")
        previous = copy.deepcopy(entry)
        target = entry
        if type is not None:
            target = next((d for d in entry.get("details") or [] if d.get("type") == type), None)
            if target is None:
                return _err("NOT_FOUND", f"Athlete {athlete_id} has no '{type}' notification entry.")
        target.update(values)
        result: dict[str, Any] = {"athlete_id": athlete_id, "previous": previous, "updated": entry}
        if dry_run:
            return {**result, "dry_run": True}
        put = await client.put("/notification/v1/coachSettings", json=entries)
        if put.is_error:
            return _api_err(put)
        return result
