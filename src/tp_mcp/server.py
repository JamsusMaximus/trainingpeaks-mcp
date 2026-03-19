"""MCP Server implementation for TrainingPeaks."""

import asyncio
import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
)

from tp_mcp.auth import get_credential, validate_auth
from tp_mcp.client.context import athlete_override
from tp_mcp.tools import (
    tp_add_workout_comment,
    tp_analyze_workout,
    tp_auth_status,
    tp_copy_workout,
    tp_create_availability,
    tp_create_equipment,
    tp_create_event,
    tp_create_library,
    tp_create_library_item,
    tp_create_note,
    tp_create_workout,
    tp_delete_availability,
    tp_delete_equipment,
    tp_delete_event,
    tp_delete_library,
    tp_delete_note,
    tp_delete_workout,
    tp_get_athlete_settings,
    tp_get_atp,
    tp_get_availability,
    tp_get_equipment,
    tp_get_events,
    tp_get_fitness,
    tp_get_focus_event,
    tp_get_libraries,
    tp_get_library_item,
    tp_get_library_items,
    tp_get_metrics,
    tp_get_next_event,
    tp_get_nutrition,
    tp_get_peaks,
    tp_get_pool_length_settings,
    tp_get_profile,
    tp_get_weekly_summary,
    tp_get_workout,
    tp_get_workout_comments,
    tp_get_workout_prs,
    tp_get_workout_types,
    tp_get_workouts,
    tp_list_athletes,
    tp_log_metrics,
    tp_refresh_auth,
    tp_reorder_workouts,
    tp_schedule_library_workout,
    tp_update_equipment,
    tp_update_event,
    tp_update_ftp,
    tp_update_hr_zones,
    tp_update_library_item,
    tp_update_nutrition,
    tp_update_speed_zones,
    tp_update_workout,
    tp_validate_structure,
)
from tp_mcp.tools.workouts import SPORT_TYPE_MAP

# Configure logging to stderr (stdout is used for MCP protocol)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("tp-mcp")

# Create the MCP server
server = Server("trainingpeaks-mcp")

STRUCTURE_DESCRIPTION = (
    "Interval structure as a JSON object or string."
    ' Format: {"steps": [...], "primaryIntensityMetric":'
    ' "percentOfFtp"|"percentOfThresholdHr"|"percentOfThresholdPace"}.'
    " Each step is either a single interval or a repetition block."
    ' SINGLE STEP: {"name": "Endurance", "duration_seconds": 1200,'
    ' "intensity_min": 65, "intensity_max": 75,'
    ' "intensityClass": "active"}.'
    ' REPETITION BLOCK: {"type": "repetition", "reps": 5, "steps": ['
    '{"name": "VO2max", "duration_seconds": 180,'
    ' "intensity_min": 106, "intensity_max": 120,'
    ' "intensityClass": "active"},'
    ' {"name": "Spin", "duration_seconds": 180,'
    ' "intensity_min": 40, "intensity_max": 50,'
    ' "intensityClass": "rest"}]}.'
    " FOR MULTIPLE SETS separated by longer recovery, alternate"
    " repetition blocks with single rest steps:"
    ' [{"type": "repetition", "reps": 4, "steps": [...]},'
    ' {"name": "Block Recovery", "duration_seconds": 600,'
    ' "intensity_min": 45, "intensity_max": 55,'
    ' "intensityClass": "rest"},'
    ' {"type": "repetition", "reps": 4, "steps": [...]}].'
    " intensityClass values: warmUp, active (work intervals),"
    " rest (all recovery), coolDown, other."
    " Intensity values are % of threshold (FTP/HR/pace)."
    " Optional per-step: cadence_min, cadence_max (rpm)."
)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------
TOOLS = [
    # --- Auth & Profile ---
    Tool(
        name="tp_auth_status",
        description="Check auth status. Use only when other tools return auth errors.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="tp_get_profile",
        description="Get athlete profile. Rarely needed - other tools work without it.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="tp_refresh_auth",
        description="Refresh auth by extracting cookie from user's browser. Use when other tools return auth errors.",
        inputSchema={
            "type": "object",
            "properties": {
                "browser": {
                    "type": "string",
                    "enum": ["auto", "chrome", "firefox", "safari", "edge"],
                    "description": "Browser to extract from. Use 'auto' to try all.",
                    "default": "auto",
                },
            },
            "required": [],
        },
    ),
    # --- Workouts ---
    Tool(
        name="tp_get_workouts",
        description="List workouts in date range. Query only days needed. Max 90 days.",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                "type": {
                    "type": "string",
                    "enum": ["all", "planned", "completed"],
                    "description": "Filter: all, planned, or completed",
                    "default": "all",
                },
            },
            "required": ["start_date", "end_date"],
        },
    ),
    Tool(
        name="tp_get_workout",
        description="Get workout details by ID. Use after tp_get_workouts.",
        inputSchema={
            "type": "object",
            "properties": {
                "workout_id": {"type": "string", "description": "Workout ID"},
            },
            "required": ["workout_id"],
        },
    ),
    Tool(
        name="tp_create_workout",
        description=(
            "Create a planned workout with optional interval structure. "
            "Duration auto-computed from structure if not provided."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "sport": {"type": "string", "enum": list(SPORT_TYPE_MAP.keys())},
                "title": {"type": "string", "description": "Workout title"},
                "duration_minutes": {
                    "type": "integer",
                    "description": "Planned duration in minutes (optional if structure provided)",
                },
                "description": {"type": "string", "description": "Optional description"},
                "distance_km": {"type": "number", "description": "Optional distance in km"},
                "tss_planned": {"type": "number", "description": "Optional planned TSS"},
                "structure": {
                    "type": ["object", "string"],
                    "description": STRUCTURE_DESCRIPTION,
                },
                "subtype_id": {
                    "type": "integer",
                    "description": "Workout subtype ID from tp_get_workout_types",
                },
                "tags": {"type": "string", "description": "Optional comma-separated tags"},
                "feeling": {"type": "integer", "description": "Feeling score 0-10"},
                "rpe": {"type": "integer", "description": "RPE score 1-10"},
            },
            "required": ["date", "sport", "title"],
        },
    ),
    Tool(
        name="tp_update_workout",
        description="Update fields of an existing workout. Fetches existing, merges, then saves.",
        inputSchema={
            "type": "object",
            "properties": {
                "workout_id": {"type": "string", "description": "Workout ID"},
                "sport": {"type": "string", "enum": list(SPORT_TYPE_MAP.keys())},
                "subtype_id": {"type": "integer"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "duration_minutes": {"type": "number"},
                "distance_km": {"type": "number"},
                "tss_planned": {"type": "number"},
                "tags": {"type": "string"},
                "athlete_comment": {"type": "string"},
                "coach_comment": {"type": "string"},
                "feeling": {"type": "integer", "description": "0-10"},
                "rpe": {"type": "integer", "description": "1-10"},
                "structure": {"type": ["object", "string"]},
            },
            "required": ["workout_id"],
        },
    ),
    Tool(
        name="tp_delete_workout",
        description="Delete a workout.",
        inputSchema={
            "type": "object",
            "properties": {"workout_id": {"type": "string"}},
            "required": ["workout_id"],
        },
    ),
    Tool(
        name="tp_copy_workout",
        description="Copy a workout to a new date. Copies structure, description, planned fields.",
        inputSchema={
            "type": "object",
            "properties": {
                "workout_id": {"type": "string", "description": "Source workout ID"},
                "target_date": {"type": "string", "description": "YYYY-MM-DD"},
                "title": {"type": "string", "description": "Optional title override"},
            },
            "required": ["workout_id", "target_date"],
        },
    ),
    Tool(
        name="tp_reorder_workouts",
        description="Reorder workouts on a given day.",
        inputSchema={
            "type": "object",
            "properties": {
                "workout_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Workout IDs in desired display order",
                },
            },
            "required": ["workout_ids"],
        },
    ),
    Tool(
        name="tp_get_workout_comments",
        description="Get comments on a workout.",
        inputSchema={
            "type": "object",
            "properties": {"workout_id": {"type": "string"}},
            "required": ["workout_id"],
        },
    ),
    Tool(
        name="tp_add_workout_comment",
        description="Add a comment to a workout.",
        inputSchema={
            "type": "object",
            "properties": {
                "workout_id": {"type": "string"},
                "comment": {"type": "string"},
            },
            "required": ["workout_id", "comment"],
        },
    ),
    Tool(
        name="tp_validate_structure",
        description=(
            "Validate workout interval structure without creating a workout."
            " Returns block count, duration, estimated IF/TSS."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "structure": {
                    "type": "string",
                    "description": (
                        "Structure JSON string to validate - same format"
                        " as the structure field in tp_create_workout."
                    ),
                },
            },
            "required": ["structure"],
        },
    ),
    # --- Analysis & Peaks ---
    Tool(
        name="tp_get_workout_prs",
        description="Get PRs set during a specific workout.",
        inputSchema={
            "type": "object",
            "properties": {"workout_id": {"type": "string"}},
            "required": ["workout_id"],
        },
    ),
    Tool(
        name="tp_get_peaks",
        description="Get top performances by type. For comparing PRs over time.",
        inputSchema={
            "type": "object",
            "properties": {
                "sport": {"type": "string", "enum": ["Bike", "Run"]},
                "pr_type": {"type": "string", "description": "Bike: power1min/5min/20min. Run: speed5K/10K/Half"},
                "days": {"type": "integer", "default": 3650},
            },
            "required": ["sport", "pr_type"],
        },
    ),
    Tool(
        name="tp_analyze_workout",
        description="Get workout analysis: metrics, zones, laps. Saves full time-series to JSON file.",
        inputSchema={
            "type": "object",
            "properties": {"workout_id": {"type": "string"}},
            "required": ["workout_id"],
        },
    ),
    # --- Fitness & Summary ---
    Tool(
        name="tp_get_fitness",
        description="Get fitness/fatigue trend (CTL/ATL/TSB). Supports historical date ranges.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer", "default": 90,
                    "description": "Days from today. Ignored if dates provided.",
                },
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": [],
        },
    ),
    Tool(
        name="tp_get_weekly_summary",
        description="Combined view of workouts + fitness for a week. Totals TSS, duration, end-of-week CTL/ATL/TSB.",
        inputSchema={
            "type": "object",
            "properties": {
                "week_of": {
                    "type": "string",
                    "description": "Date in the target week (YYYY-MM-DD). Defaults to current.",
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="tp_get_atp",
        description="Get Annual Training Plan - weekly TSS targets, training periods, races. Max 90 days.",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["start_date", "end_date"],
        },
    ),
    # --- Athlete Settings ---
    Tool(
        name="tp_get_athlete_settings",
        description="Get athlete settings: FTP, thresholds, zones, profile.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="tp_update_ftp",
        description="Update FTP and recalculate Coggan 5-zone power model.",
        inputSchema={
            "type": "object",
            "properties": {"ftp": {"type": "integer", "description": "FTP in watts"}},
            "required": ["ftp"],
        },
    ),
    Tool(
        name="tp_update_hr_zones",
        description="Update heart rate zones.",
        inputSchema={
            "type": "object",
            "properties": {
                "threshold_hr": {"type": "integer"},
                "max_hr": {"type": "integer"},
                "resting_hr": {"type": "integer"},
                "workout_type": {"type": "string", "enum": ["general", "bike"], "default": "general"},
            },
            "required": [],
        },
    ),
    Tool(
        name="tp_update_speed_zones",
        description="Update run/swim pace zones.",
        inputSchema={
            "type": "object",
            "properties": {
                "run_threshold_pace": {"type": "string", "description": "e.g. '4:30/km'"},
                "swim_threshold_pace": {"type": "string", "description": "e.g. '1:45/100m'"},
            },
            "required": [],
        },
    ),
    Tool(
        name="tp_update_nutrition",
        description="Update daily planned calories.",
        inputSchema={
            "type": "object",
            "properties": {"planned_calories": {"type": "integer"}},
            "required": ["planned_calories"],
        },
    ),
    Tool(
        name="tp_get_pool_length_settings",
        description="Get pool length settings.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    # --- Health Metrics ---
    Tool(
        name="tp_log_metrics",
        description="Log health metrics (weight, HRV, sleep, steps, etc.) for a date.",
        inputSchema={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "weight_kg": {"type": "number"},
                "pulse": {"type": "integer"},
                "hrv": {"type": "number"},
                "sleep_hours": {"type": "number"},
                "spo2": {"type": "number"},
                "steps": {"type": "integer"},
                "rmr": {"type": "integer"},
                "injury": {"type": "integer", "description": "1-10"},
            },
            "required": ["date"],
        },
    ),
    Tool(
        name="tp_get_metrics",
        description="Get health metrics for a date range.",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["start_date", "end_date"],
        },
    ),
    Tool(
        name="tp_get_nutrition",
        description="Get nutrition data for a date range.",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["start_date", "end_date"],
        },
    ),
    # --- Equipment ---
    Tool(
        name="tp_get_equipment",
        description="List equipment (bikes, shoes).",
        inputSchema={
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["bike", "shoe", "all"], "default": "all"},
            },
            "required": [],
        },
    ),
    Tool(
        name="tp_create_equipment",
        description="Add new equipment (bike or shoe).",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "type": {"type": "string", "enum": ["bike", "shoe"]},
                "brand": {"type": "string"},
                "model": {"type": "string"},
                "notes": {"type": "string"},
                "date_of_purchase": {"type": "string", "description": "YYYY-MM-DD"},
                "starting_distance_km": {"type": "number"},
                "max_distance_km": {"type": "number"},
                "is_default": {"type": "boolean", "default": False},
                "wheels": {"type": "string", "description": "Bike only"},
                "crank_length_mm": {"type": "number", "description": "Bike only"},
            },
            "required": ["name", "type"],
        },
    ),
    Tool(
        name="tp_update_equipment",
        description="Update equipment details.",
        inputSchema={
            "type": "object",
            "properties": {
                "equipment_id": {"type": "string"},
                "name": {"type": "string"},
                "brand": {"type": "string"},
                "model": {"type": "string"},
                "notes": {"type": "string"},
                "retired": {"type": "boolean"},
                "is_default": {"type": "boolean"},
                "max_distance_km": {"type": "number"},
                "wheels": {"type": "string"},
                "crank_length_mm": {"type": "number"},
            },
            "required": ["equipment_id"],
        },
    ),
    Tool(
        name="tp_delete_equipment",
        description="Delete equipment.",
        inputSchema={
            "type": "object",
            "properties": {"equipment_id": {"type": "string"}},
            "required": ["equipment_id"],
        },
    ),
    # --- Events & Calendar ---
    Tool(
        name="tp_get_focus_event",
        description="Get the A-priority focus event with goals and results.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="tp_get_next_event",
        description="Get the nearest future planned event.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="tp_get_events",
        description="List events in a date range.",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["start_date", "end_date"],
        },
    ),
    Tool(
        name="tp_create_event",
        description="Create a race/event with priority (A/B/C) and CTL target.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "event_type": {
                    "type": "string",
                    "description": (
                        "e.g. Triathlon, MultisportTriathlon, RoadRunning,"
                        " RoadCycling, MountainBiking, OpenWaterSwimming, Other"
                    ),
                },
                "priority": {"type": "string", "enum": ["A", "B", "C"]},
                "distance_km": {"type": "number"},
                "ctl_target": {"type": "number"},
                "description": {"type": "string"},
            },
            "required": ["name", "date"],
        },
    ),
    Tool(
        name="tp_update_event",
        description="Update an event.",
        inputSchema={
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "name": {"type": "string"},
                "date": {"type": "string"},
                "event_type": {"type": "string"},
                "priority": {"type": "string", "enum": ["A", "B", "C"]},
                "distance_km": {"type": "number"},
                "ctl_target": {"type": "number"},
                "description": {"type": "string"},
            },
            "required": ["event_id"],
        },
    ),
    Tool(
        name="tp_delete_event",
        description="Delete an event.",
        inputSchema={
            "type": "object",
            "properties": {"event_id": {"type": "string"}},
            "required": ["event_id"],
        },
    ),
    Tool(
        name="tp_create_note",
        description="Create a calendar note.",
        inputSchema={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "title": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["date", "title"],
        },
    ),
    Tool(
        name="tp_delete_note",
        description="Delete a calendar note.",
        inputSchema={
            "type": "object",
            "properties": {"note_id": {"type": "string"}},
            "required": ["note_id"],
        },
    ),
    Tool(
        name="tp_get_availability",
        description="Get availability entries for a date range.",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["start_date", "end_date"],
        },
    ),
    Tool(
        name="tp_create_availability",
        description="Mark dates as unavailable or limited.",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                "limited": {"type": "boolean", "default": False},
                "sport_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Available sport types if limited",
                },
            },
            "required": ["start_date", "end_date"],
        },
    ),
    Tool(
        name="tp_delete_availability",
        description="Remove an availability entry.",
        inputSchema={
            "type": "object",
            "properties": {"availability_id": {"type": "string"}},
            "required": ["availability_id"],
        },
    ),
    # --- Workout Types ---
    Tool(
        name="tp_get_workout_types",
        description="List all sport types and subtypes with IDs. Use to find subtype_id for create/update.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    # --- Workout Library ---
    Tool(
        name="tp_get_libraries",
        description="List workout library folders.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="tp_get_library_items",
        description="List templates in a workout library.",
        inputSchema={
            "type": "object",
            "properties": {"library_id": {"type": "string"}},
            "required": ["library_id"],
        },
    ),
    Tool(
        name="tp_get_library_item",
        description="Get full template details including structure.",
        inputSchema={
            "type": "object",
            "properties": {
                "library_id": {"type": "string"},
                "item_id": {"type": "string"},
            },
            "required": ["library_id", "item_id"],
        },
    ),
    Tool(
        name="tp_create_library",
        description="Create a workout library folder.",
        inputSchema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    ),
    Tool(
        name="tp_delete_library",
        description="Delete a library folder and all templates.",
        inputSchema={
            "type": "object",
            "properties": {"library_id": {"type": "string"}},
            "required": ["library_id"],
        },
    ),
    Tool(
        name="tp_create_library_item",
        description="Save a workout template to a library.",
        inputSchema={
            "type": "object",
            "properties": {
                "library_id": {"type": "string"},
                "name": {"type": "string"},
                "sport_family_id": {"type": "integer"},
                "sport_type_id": {"type": "integer"},
                "duration_hours": {"type": "number"},
                "tss": {"type": "number"},
                "description": {"type": "string"},
                "structure": {"type": "object", "description": "Interval structure (nested object)"},
            },
            "required": ["library_id", "name", "sport_family_id", "sport_type_id"],
        },
    ),
    Tool(
        name="tp_update_library_item",
        description="Edit a workout template.",
        inputSchema={
            "type": "object",
            "properties": {
                "library_id": {"type": "string"},
                "item_id": {"type": "string"},
                "name": {"type": "string"},
                "duration_hours": {"type": "number"},
                "tss": {"type": "number"},
                "description": {"type": "string"},
                "structure": {"type": "object"},
            },
            "required": ["library_id", "item_id"],
        },
    ),
    Tool(
        name="tp_schedule_library_workout",
        description="Schedule a library template to a calendar date.",
        inputSchema={
            "type": "object",
            "properties": {
                "library_id": {"type": "string"},
                "item_id": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["library_id", "item_id", "date"],
        },
    ),
    Tool(
        name="tp_list_athletes",
        description="List athletes available to this account (coach accounts).",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
]

# ---------------------------------------------------------------------------
# Coach account support: inject 'athlete' parameter into all applicable tools
# ---------------------------------------------------------------------------
_ATHLETE_EXEMPT_TOOLS = {
    "tp_auth_status", "tp_refresh_auth", "tp_validate_structure",
    "tp_list_athletes", "tp_get_workout_types",
}

_ATHLETE_PARAM = {
    "type": "string",
    "description": "Target athlete name or ID (coach accounts only). Omit to use your own profile.",
}

for _tool in TOOLS:
    if _tool.name not in _ATHLETE_EXEMPT_TOOLS:
        _tool.inputSchema["properties"]["athlete"] = _ATHLETE_PARAM


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return TOOLS


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

# Map tool names to handler functions for cleaner dispatch
_TOOL_HANDLERS: dict[str, Any] = {}


def _handler(name: str):
    """Decorator to register a tool handler."""
    def decorator(fn):
        _TOOL_HANDLERS[name] = fn
        return fn
    return decorator


# --- Auth & Profile ---
@_handler("tp_auth_status")
async def _h_auth_status(args): return await tp_auth_status()

@_handler("tp_get_profile")
async def _h_get_profile(args): return await tp_get_profile()

@_handler("tp_list_athletes")
async def _h_list_athletes(args): return await tp_list_athletes()

@_handler("tp_refresh_auth")
async def _h_refresh_auth(args): return await tp_refresh_auth(browser=args.get("browser", "auto"))

# --- Workouts ---
@_handler("tp_get_workouts")
async def _h_get_workouts(args):
    return await tp_get_workouts(
        start_date=args["start_date"], end_date=args["end_date"],
        workout_filter=args.get("type", "all"),
    )

@_handler("tp_get_workout")
async def _h_get_workout(args): return await tp_get_workout(workout_id=args["workout_id"])

@_handler("tp_create_workout")
async def _h_create_workout(args):
    return await tp_create_workout(
        date_str=args["date"], sport=args["sport"], title=args["title"],
        duration_minutes=args.get("duration_minutes"),
        description=args.get("description"), distance_km=args.get("distance_km"),
        tss_planned=args.get("tss_planned"), structure=args.get("structure"),
        subtype_id=args.get("subtype_id"), tags=args.get("tags"),
        feeling=args.get("feeling"), rpe=args.get("rpe"),
    )

@_handler("tp_update_workout")
async def _h_update_workout(args):
    return await tp_update_workout(
        workout_id=args["workout_id"], sport=args.get("sport"),
        subtype_id=args.get("subtype_id"), title=args.get("title"),
        description=args.get("description"), date=args.get("date"),
        duration_minutes=args.get("duration_minutes"),
        distance_km=args.get("distance_km"), tss_planned=args.get("tss_planned"),
        tags=args.get("tags"), athlete_comment=args.get("athlete_comment"),
        coach_comment=args.get("coach_comment"), feeling=args.get("feeling"),
        rpe=args.get("rpe"), structure=args.get("structure"),
    )

@_handler("tp_delete_workout")
async def _h_delete_workout(args): return await tp_delete_workout(workout_id=args["workout_id"])

@_handler("tp_copy_workout")
async def _h_copy_workout(args):
    return await tp_copy_workout(
        workout_id=args["workout_id"], target_date=args["target_date"],
        title=args.get("title"),
    )

@_handler("tp_reorder_workouts")
async def _h_reorder(args): return await tp_reorder_workouts(workout_ids=args["workout_ids"])

@_handler("tp_get_workout_comments")
async def _h_get_comments(args): return await tp_get_workout_comments(workout_id=args["workout_id"])

@_handler("tp_add_workout_comment")
async def _h_add_comment(args):
    return await tp_add_workout_comment(workout_id=args["workout_id"], comment=args["comment"])

@_handler("tp_validate_structure")
async def _h_validate_structure(args): return await tp_validate_structure(structure=args["structure"])

# --- Analysis & Peaks ---
@_handler("tp_get_workout_prs")
async def _h_get_prs(args): return await tp_get_workout_prs(workout_id=args["workout_id"])

@_handler("tp_get_peaks")
async def _h_get_peaks(args):
    return await tp_get_peaks(sport=args["sport"], pr_type=args["pr_type"], days=args.get("days", 3650))

@_handler("tp_analyze_workout")
async def _h_analyze(args): return await tp_analyze_workout(workout_id=args["workout_id"])

# --- Fitness & Summary ---
@_handler("tp_get_fitness")
async def _h_get_fitness(args):
    return await tp_get_fitness(
        days=args.get("days", 90), start_date=args.get("start_date"),
        end_date=args.get("end_date"),
    )

@_handler("tp_get_weekly_summary")
async def _h_weekly_summary(args): return await tp_get_weekly_summary(week_of=args.get("week_of"))

@_handler("tp_get_atp")
async def _h_get_atp(args): return await tp_get_atp(start_date=args["start_date"], end_date=args["end_date"])

# --- Athlete Settings ---
@_handler("tp_get_athlete_settings")
async def _h_get_settings(args): return await tp_get_athlete_settings()

@_handler("tp_update_ftp")
async def _h_update_ftp(args): return await tp_update_ftp(ftp=args["ftp"])

@_handler("tp_update_hr_zones")
async def _h_update_hr(args):
    return await tp_update_hr_zones(
        threshold_hr=args.get("threshold_hr"), max_hr=args.get("max_hr"),
        resting_hr=args.get("resting_hr"), workout_type=args.get("workout_type", "general"),
    )

@_handler("tp_update_speed_zones")
async def _h_update_speed(args):
    return await tp_update_speed_zones(
        run_threshold_pace=args.get("run_threshold_pace"),
        swim_threshold_pace=args.get("swim_threshold_pace"),
    )

@_handler("tp_update_nutrition")
async def _h_update_nutrition(args): return await tp_update_nutrition(planned_calories=args["planned_calories"])

@_handler("tp_get_pool_length_settings")
async def _h_pool(args): return await tp_get_pool_length_settings()

# --- Health Metrics ---
@_handler("tp_log_metrics")
async def _h_log_metrics(args):
    return await tp_log_metrics(
        date=args["date"], weight_kg=args.get("weight_kg"), pulse=args.get("pulse"),
        hrv=args.get("hrv"), sleep_hours=args.get("sleep_hours"), spo2=args.get("spo2"),
        steps=args.get("steps"), rmr=args.get("rmr"), injury=args.get("injury"),
    )

@_handler("tp_get_metrics")
async def _h_get_metrics(args):
    return await tp_get_metrics(start_date=args["start_date"], end_date=args["end_date"])

@_handler("tp_get_nutrition")
async def _h_get_nutrition(args):
    return await tp_get_nutrition(start_date=args["start_date"], end_date=args["end_date"])

# --- Equipment ---
@_handler("tp_get_equipment")
async def _h_get_equipment(args): return await tp_get_equipment(type=args.get("type", "all"))

@_handler("tp_create_equipment")
async def _h_create_equipment(args):
    return await tp_create_equipment(
        name=args["name"], type=args["type"], brand=args.get("brand"),
        model=args.get("model"), notes=args.get("notes"),
        date_of_purchase=args.get("date_of_purchase"),
        starting_distance_km=args.get("starting_distance_km"),
        max_distance_km=args.get("max_distance_km"),
        is_default=args.get("is_default", False),
        wheels=args.get("wheels"), crank_length_mm=args.get("crank_length_mm"),
    )

@_handler("tp_update_equipment")
async def _h_update_equipment(args):
    return await tp_update_equipment(
        equipment_id=args["equipment_id"], name=args.get("name"),
        brand=args.get("brand"), model=args.get("model"), notes=args.get("notes"),
        retired=args.get("retired"), is_default=args.get("is_default"),
        max_distance_km=args.get("max_distance_km"),
        wheels=args.get("wheels"), crank_length_mm=args.get("crank_length_mm"),
    )

@_handler("tp_delete_equipment")
async def _h_delete_equipment(args): return await tp_delete_equipment(equipment_id=args["equipment_id"])

# --- Events & Calendar ---
@_handler("tp_get_focus_event")
async def _h_focus_event(args): return await tp_get_focus_event()

@_handler("tp_get_next_event")
async def _h_next_event(args): return await tp_get_next_event()

@_handler("tp_get_events")
async def _h_get_events(args):
    return await tp_get_events(start_date=args["start_date"], end_date=args["end_date"])

@_handler("tp_create_event")
async def _h_create_event(args):
    return await tp_create_event(
        name=args["name"], date=args["date"], event_type=args.get("event_type"),
        priority=args.get("priority"), distance_km=args.get("distance_km"),
        ctl_target=args.get("ctl_target"), description=args.get("description"),
    )

@_handler("tp_update_event")
async def _h_update_event(args):
    return await tp_update_event(
        event_id=args["event_id"], name=args.get("name"), date=args.get("date"),
        event_type=args.get("event_type"), priority=args.get("priority"),
        distance_km=args.get("distance_km"), ctl_target=args.get("ctl_target"),
        description=args.get("description"),
    )

@_handler("tp_delete_event")
async def _h_delete_event(args): return await tp_delete_event(event_id=args["event_id"])

@_handler("tp_create_note")
async def _h_create_note(args):
    return await tp_create_note(
        date=args["date"], title=args["title"], description=args.get("description"),
    )

@_handler("tp_delete_note")
async def _h_delete_note(args): return await tp_delete_note(note_id=args["note_id"])

@_handler("tp_get_availability")
async def _h_get_avail(args):
    return await tp_get_availability(start_date=args["start_date"], end_date=args["end_date"])

@_handler("tp_create_availability")
async def _h_create_avail(args):
    return await tp_create_availability(
        start_date=args["start_date"], end_date=args["end_date"],
        limited=args.get("limited", False), sport_types=args.get("sport_types"),
    )

@_handler("tp_delete_availability")
async def _h_delete_avail(args): return await tp_delete_availability(availability_id=args["availability_id"])

# --- Workout Types ---
@_handler("tp_get_workout_types")
async def _h_workout_types(args): return await tp_get_workout_types()

# --- Workout Library ---
@_handler("tp_get_libraries")
async def _h_get_libs(args): return await tp_get_libraries()

@_handler("tp_get_library_items")
async def _h_get_lib_items(args): return await tp_get_library_items(library_id=args["library_id"])

@_handler("tp_get_library_item")
async def _h_get_lib_item(args):
    return await tp_get_library_item(library_id=args["library_id"], item_id=args["item_id"])

@_handler("tp_create_library")
async def _h_create_lib(args): return await tp_create_library(name=args["name"])

@_handler("tp_delete_library")
async def _h_delete_lib(args): return await tp_delete_library(library_id=args["library_id"])

@_handler("tp_create_library_item")
async def _h_create_lib_item(args):
    return await tp_create_library_item(
        library_id=args["library_id"], name=args["name"],
        sport_family_id=args["sport_family_id"], sport_type_id=args["sport_type_id"],
        duration_hours=args.get("duration_hours"), tss=args.get("tss"),
        description=args.get("description"), structure=args.get("structure"),
    )

@_handler("tp_update_library_item")
async def _h_update_lib_item(args):
    return await tp_update_library_item(
        library_id=args["library_id"], item_id=args["item_id"],
        name=args.get("name"), duration_hours=args.get("duration_hours"),
        tss=args.get("tss"), description=args.get("description"),
        structure=args.get("structure"),
    )

@_handler("tp_schedule_library_workout")
async def _h_schedule_lib(args):
    return await tp_schedule_library_workout(
        library_id=args["library_id"], item_id=args["item_id"], date=args["date"],
    )


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    logger.info("Tool call: %s", name)

    # Extract athlete targeting for coach accounts and set context var
    athlete_target = arguments.pop("athlete", None)
    token = athlete_override.set(athlete_target)
    try:
        handler = _TOOL_HANDLERS.get(name)
        if handler:
            result = await handler(arguments)
        else:
            result = {
                "isError": True,
                "error_code": "UNKNOWN_TOOL",
                "message": f"Unknown tool: {name}",
            }

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception:
        logger.exception("Error in tool %s", name)
        error_result = {
            "isError": True,
            "error_code": "API_ERROR",
            "message": "An internal error occurred. Check server logs.",
        }
        return [TextContent(type="text", text=json.dumps(error_result, indent=2))]
    finally:
        athlete_override.reset(token)


async def _validate_auth_on_startup() -> bool:
    """Validate authentication on server startup."""
    cred = get_credential()
    if not cred.success or not cred.cookie:
        logger.warning("No credential stored. Run 'tp-mcp auth' to authenticate.")
        return False

    result = await validate_auth(cred.cookie)
    if result.is_valid:
        logger.info("Authentication valid (athlete_id: %s)", result.athlete_id)
        return True
    else:
        logger.warning("Authentication invalid: %s", result.message)
        return False


async def run_server_async() -> None:
    """Run the MCP server (async)."""
    logger.info("Starting TrainingPeaks MCP Server")
    await _validate_auth_on_startup()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def run_server() -> int:
    """Run the MCP server (entry point)."""
    try:
        asyncio.run(run_server_async())
        return 0
    except KeyboardInterrupt:
        logger.info("Server stopped")
        return 0
    except Exception:
        logger.exception("Server error")
        return 1
