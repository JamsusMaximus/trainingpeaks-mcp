"""Timezone helpers for the naive UTC timestamps TrainingPeaks returns.

Completed-data timestamps from the TrainingPeaks and Peaksware analysis APIs
(``startTimestamp`` / ``stopTimestamp`` on an analysis, ``dateUploaded`` on a
workout file) are ISO-8601 strings with no offset, expressed in UTC. Tools
that expose them keep the raw field untouched and, when the caller passes an
IANA ``timezone``, add a ``*_local`` sibling carrying the explicit offset.
"""

import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Python < 3.11 only parses 3 or 6 fractional digits; TP/.NET can emit 7.
_FRACTION = re.compile(r"(\.\d{1,6})\d*")

TIMEZONE_PARAM_DESCRIPTION = (
    "Optional IANA timezone name (e.g. 'Europe/London', 'America/Denver'). "
    "When given, every UTC timestamp in the result gets a *_local sibling as an "
    "ISO-8601 string with offset. Raw fields are left unchanged."
)


def resolve_timezone(name: str | None) -> tuple[ZoneInfo | None, dict[str, Any] | None]:
    """Validate an IANA timezone name.

    Returns:
        ``(zone, None)`` for a valid name, ``(None, None)`` when no name was
        given, or ``(None, error_envelope)`` for an unknown name.
    """
    if name is None:
        return None, None
    text = str(name).strip()
    if not text:
        return None, None
    try:
        return ZoneInfo(text), None
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return None, {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": (
                f"Unknown timezone '{name}'. Use an IANA name such as 'Europe/London' "
                "or 'America/Denver'. (On Windows the 'tzdata' package must be installed.)"
            ),
        }


def utc_to_local(value: Any, zone: ZoneInfo) -> str | None:
    """Render a naive-UTC (or offset-bearing) ISO timestamp in ``zone``.

    Returns ``None`` for missing or unparseable input rather than raising, so a
    malformed timestamp never breaks the surrounding tool result.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    text = _FRACTION.sub(r"\1", text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(zone).isoformat()
