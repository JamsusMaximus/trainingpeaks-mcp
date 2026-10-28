"""Timezone helpers for the naive timestamps TrainingPeaks returns.

TrainingPeaks and the Peaksware analysis API return timestamps as ISO-8601
strings with no offset, and not all of them are in the same zone:

* ``startTimestamp`` / ``stopTimestamp`` on an analysis are **UTC** (verified
  live: a run started 10:37 CET reports ``startTimestamp`` 09:37:03).
* ``dateUploaded`` on a workout file (exposed as ``uploaded_at``) is
  **TrainingPeaks server time, America/Denver** (verified live 2026-10-26..28:
  a file named ``...2026-10-27-10-57-53-135Z...`` carries
  ``dateUploaded`` 2026-10-27T04:57:53, i.e. UTC-6 / MDT).

Tools keep the raw field untouched and, when the caller passes an IANA
``timezone``, add a ``*_local`` sibling carrying the explicit offset, converted
from whichever source zone the field is actually in.
"""

import re
from datetime import datetime, timezone, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Python < 3.11 only parses 3 or 6 fractional digits; TP/.NET can emit 7.
_FRACTION = re.compile(r"(\.\d{1,6})\d*")

# Zone of TrainingPeaks' servers; ``dateUploaded`` is stamped in it (DST-aware).
TP_SERVER_TIMEZONE = "America/Denver"

TIMEZONE_PARAM_DESCRIPTION = (
    "Optional IANA timezone name (e.g. 'Europe/London', 'America/Denver'). "
    "When given, every timestamp in the result gets a *_local sibling as an "
    "ISO-8601 string with offset, converted from the field's source zone (stated "
    "in the tool description). Raw fields are left unchanged."
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


def naive_to_local(value: Any, zone: ZoneInfo, source: tzinfo) -> str | None:
    """Render an ISO timestamp in ``zone``, reading a naive value as ``source`` time.

    An explicit offset or ``Z`` in the input wins over ``source``. Returns
    ``None`` for missing or unparseable input rather than raising, so a
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
        parsed = parsed.replace(tzinfo=source)
    return parsed.astimezone(zone).isoformat()


def utc_to_local(value: Any, zone: ZoneInfo) -> str | None:
    """Render a naive-UTC ISO timestamp (analysis ``startTimestamp`` etc.) in ``zone``."""
    return naive_to_local(value, zone, timezone.utc)


def server_time_to_local(value: Any, zone: ZoneInfo) -> str | None:
    """Render a naive TrainingPeaks-server-time ISO timestamp (``dateUploaded``) in ``zone``.

    The source zone is America/Denver with its DST rules applied to the
    timestamp itself (MDT, UTC-6, in summer; MST, UTC-7, in winter).
    """
    return naive_to_local(value, zone, ZoneInfo(TP_SERVER_TIMEZONE))
