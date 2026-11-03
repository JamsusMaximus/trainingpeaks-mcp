"""tp_get_notifications - the in-app notification feed (the bell icon in the web app).

Verified against the live API:
  • GET /notification/v2/notifications/{days} → {notifications, newNotificationCount, unreadNotificationCount}
    where `{days}` is the look-back window (3 returns 3 days, 0 returns nothing).
  • Each entry's `itemData` is a JSON string whose shape depends on `notificationType`.
  • The web app's type buttons and search box filter client-side; "Grouped" uses /notification/v3/group/{days}.
"""

import json
import logging
from typing import Any

from tp_mcp.client import TPClient

logger = logging.getLogger("tp-mcp")

MAX_DAYS = 365

# Fields kept from each notification's `itemData`, per item type. The raw blobs are large (sequence summaries,
# feed items), so only the fields that answer "what happened" are returned.
_ITEM_FIELDS = {
    "Workout": (
        "workoutId", "workoutDay", "title", "sportType", "athleteId", "isCompleted",
        "totalTimeCompleted", "totalTimePlanned", "distanceCompleted", "distancePlanned",
        "tssCompleted", "tssPlanned", "ifCompleted", "ifPlanned", "totalSetsCompleted", "totalSets",
        "totalExercisesCompleted", "totalExercises",
    ),
    "Availability": ("id", "startDate", "endDate", "type", "reason", "description", "availableSportTypes"),
    "Threshold": ("workoutId", "workoutDay", "sportType", "threshold", "oldThreshold", "thresholdType",
                  "newZonesApplied"),
}


def _err(code: str, message: str) -> dict[str, Any]:
    return {"isError": True, "error_code": code, "message": message}


def _item(notification: dict[str, Any]) -> dict[str, Any]:
    """The notification's `itemData` (a JSON string) reduced to its useful fields."""
    raw = notification.get("itemData")
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    fields = _ITEM_FIELDS.get(str(notification.get("itemDataType")))
    if fields is None:
        return data
    return {k: data[k] for k in fields if data.get(k) is not None}


def _shape(notification: dict[str, Any]) -> dict[str, Any]:
    first = notification.get("modifiedByFirstName") or ""
    last = notification.get("modifiedByLastName") or ""
    return {
        "id": notification.get("id"),
        "timestamp": notification.get("timestamp"),
        "type": notification.get("notificationType"),
        "item_type": notification.get("itemDataType"),
        "item_id": notification.get("itemId"),
        "is_read": notification.get("isRead"),
        "from": f"{first} {last}".strip() or None,
        "from_person_id": notification.get("modifiedByPersonId"),
        "about_person_id": notification.get("aboutPersonId"),
        "item": _item(notification),
    }


async def tp_get_notifications(
    days: int = 14,
    unread_only: bool = False,
    type: str | None = None,
) -> dict[str, Any]:
    """Get the notification feed (the bell icon): comments, availability, threshold changes, completions.

    Args:
        days: Look-back window in days (default 14, the web app's default; max 365).
        unread_only: Only notifications not yet marked read.
        type: Only one notification type, e.g. WorkoutComment, AvailabilityCreated, ThresholdChange.

    Returns:
        Dict with `notifications` (newest first), `unread_count` and `types` present in the feed.
    """
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= MAX_DAYS:
        return _err("VALIDATION_ERROR", f"days must be between 1 and {MAX_DAYS}.")

    async with TPClient() as client:
        response = await client.get(f"/notification/v2/notifications/{days}")
        if response.is_error:
            return _err(response.error_code.value if response.error_code else "API_ERROR", response.message)

    data = response.data if isinstance(response.data, dict) else {}
    entries = [n for n in data.get("notifications") or [] if isinstance(n, dict)]
    types = sorted({str(n.get("notificationType")) for n in entries})
    if unread_only:
        entries = [n for n in entries if not n.get("isRead")]
    if type:
        entries = [n for n in entries if n.get("notificationType") == type]
    entries.sort(key=lambda n: str(n.get("timestamp")), reverse=True)

    return {
        "days": days,
        "unread_count": data.get("unreadNotificationCount"),
        "count": len(entries),
        "types": types,
        "notifications": [_shape(n) for n in entries],
    }
