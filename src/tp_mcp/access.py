"""Least-privilege access policy for the TrainingPeaks MCP server.

This module gates which tools the AI assistant can see and call, so a
confused or prompt-injected model cannot modify or destroy TrainingPeaks
data unless the human operator has explicitly opted in.

Configuration is read from the process environment (set it in the
`env` block of your Claude Desktop / MCP client config):

- TP_MCP_MODE:
    "read" / "readonly"  -> only read-only tools (+ auth refresh)
    "write"              -> read + create/update tools, but NO deletes
    "full"               -> everything (default; backwards compatible)

- TP_MCP_DISABLED_TOOLS:
    Comma-separated exact tool names to disable regardless of mode.
    Example: "tp_upload_workout_file,tp_delete_workout"

SECURITY DESIGN:
- Fail safe: a tool that is not explicitly known is treated as WRITE
  (hidden in read-only mode), and any unknown tool whose name implies
  removal is treated as DELETE (hidden unless mode is "full").
- Two enforcement points: tools are filtered out of `list_tools` (the
  model never sees them) AND rejected in `call_tool` (defense in depth,
  in case a name is called directly).
"""

import os
from enum import Enum


class AccessLevel(str, Enum):
    """Capability tier of a tool."""

    READ = "read"       # fetch/inspect only, no server-side mutation
    WRITE = "write"     # create / update / log (reversible-ish mutation)
    DELETE = "delete"   # destructive: permanently removes data
    AUTH = "auth"       # local auth maintenance (no TP data mutation)


MODE_ENV_VAR = "TP_MCP_MODE"
DISABLED_ENV_VAR = "TP_MCP_DISABLED_TOOLS"

# Explicit, audited classification. WRITE is intentionally the implicit
# default (everything not listed here), so the maps below only need to
# enumerate READ, DELETE, and AUTH.
_READ_TOOLS: frozenset[str] = frozenset({
    "tp_analyze_workout", "tp_auth_status", "tp_download_workout_file",
    "tp_get_athlete_settings", "tp_get_atp", "tp_get_availability",
    "tp_get_equipment", "tp_get_events", "tp_get_fitness", "tp_get_focus_event",
    "tp_get_libraries", "tp_get_library_item", "tp_get_library_items",
    "tp_get_metrics", "tp_get_next_event", "tp_get_note", "tp_get_note_comments",
    "tp_get_nutrition", "tp_get_peaks", "tp_get_pool_length_settings",
    "tp_get_profile", "tp_get_strength_summary", "tp_get_weekly_summary",
    "tp_get_workout", "tp_get_workout_comments", "tp_get_workout_note",
    "tp_get_workout_prs", "tp_get_workout_types", "tp_get_workouts",
    "tp_get_zone_methods", "tp_list_athletes", "tp_list_athletes_in_group",
    "tp_list_groups", "tp_list_notes", "tp_search_exercises",
    "tp_validate_structure",
})

_DELETE_TOOLS: frozenset[str] = frozenset({
    "tp_delete_availability", "tp_delete_equipment", "tp_delete_event",
    "tp_delete_group", "tp_delete_library", "tp_delete_note",
    "tp_delete_strength_workout", "tp_delete_workout", "tp_delete_workout_file",
})

_AUTH_TOOLS: frozenset[str] = frozenset({"tp_refresh_auth"})

# Known tools whose name would otherwise trip the destructive-hint heuristic
# below but are really reversible writes (e.g. group-membership management,
# symmetric with tp_add_athletes_to_group).
_WRITE_TOOLS: frozenset[str] = frozenset({"tp_remove_athletes_from_group"})

# Substrings that force an *unknown* tool to the DELETE tier (fail safe).
# Explicit classification above always wins over this heuristic.
_DESTRUCTIVE_HINTS = ("delete", "remove", "clear", "purge", "destroy")

_MODE_LEVELS: dict[str, frozenset[AccessLevel]] = {
    "read": frozenset({AccessLevel.READ, AccessLevel.AUTH}),
    "readonly": frozenset({AccessLevel.READ, AccessLevel.AUTH}),
    "write": frozenset({AccessLevel.READ, AccessLevel.AUTH, AccessLevel.WRITE}),
    "full": frozenset(
        {AccessLevel.READ, AccessLevel.AUTH, AccessLevel.WRITE, AccessLevel.DELETE}
    ),
}

DEFAULT_MODE = "full"  # backwards compatible; override with TP_MCP_MODE


def classify(tool_name: str) -> AccessLevel:
    """Return the capability tier for a tool name (fail safe)."""
    if tool_name in _READ_TOOLS:
        return AccessLevel.READ
    if tool_name in _DELETE_TOOLS:
        return AccessLevel.DELETE
    if tool_name in _AUTH_TOOLS:
        return AccessLevel.AUTH
    if tool_name in _WRITE_TOOLS:
        return AccessLevel.WRITE
    # Unknown tool: fail safe. Treat removal-shaped names as destructive,
    # everything else as a write (hidden in read-only mode).
    if any(hint in tool_name for hint in _DESTRUCTIVE_HINTS):
        return AccessLevel.DELETE
    return AccessLevel.WRITE


def current_mode() -> str:
    """Resolved mode name from the environment (lowercased)."""
    mode = os.environ.get(MODE_ENV_VAR, DEFAULT_MODE).strip().lower()
    return mode if mode in _MODE_LEVELS else DEFAULT_MODE


def _allowed_levels() -> frozenset[AccessLevel]:
    return _MODE_LEVELS[current_mode()]


def _disabled_tools() -> frozenset[str]:
    raw = os.environ.get(DISABLED_ENV_VAR, "")
    return frozenset(name.strip() for name in raw.split(",") if name.strip())


def is_tool_allowed(tool_name: str) -> bool:
    """Whether the tool may be exposed/called under the current policy."""
    if tool_name in _disabled_tools():
        return False
    return classify(tool_name) in _allowed_levels()


def denial_reason(tool_name: str) -> str:
    """Human-readable reason a tool is blocked (safe to show the model)."""
    if tool_name in _disabled_tools():
        return (
            f"Tool '{tool_name}' is disabled via {DISABLED_ENV_VAR}. "
            "Ask the human operator to enable it if this is intended."
        )
    level = classify(tool_name)
    return (
        f"Tool '{tool_name}' requires a higher privilege ({level.value}) than the "
        f"current {MODE_ENV_VAR}='{current_mode()}' allows. The human operator "
        f"must raise {MODE_ENV_VAR} (read < write < full) to permit this."
    )


def policy_summary() -> str:
    """One-line description for startup logging."""
    disabled = _disabled_tools()
    extra = f", {len(disabled)} tool(s) explicitly disabled" if disabled else ""
    return f"access policy: {MODE_ENV_VAR}='{current_mode()}'{extra}"
