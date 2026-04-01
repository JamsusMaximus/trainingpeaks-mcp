"""MCP tools for TrainingPeaks."""

from tp_mcp.tools.analyze import tp_analyze_workout
from tp_mcp.tools.atp import tp_get_atp
from tp_mcp.tools.auth_status import tp_auth_status
from tp_mcp.tools.equipment import (
    tp_create_equipment,
    tp_delete_equipment,
    tp_get_equipment,
    tp_update_equipment,
)
from tp_mcp.tools.events import (
    tp_create_availability,
    tp_create_event,
    tp_create_note,
    tp_delete_availability,
    tp_delete_event,
    tp_delete_note,
    tp_get_availability,
    tp_get_events,
    tp_get_focus_event,
    tp_get_next_event,
    tp_update_event,
)
from tp_mcp.tools.fitness import tp_get_fitness
from tp_mcp.tools.library import (
    tp_create_library,
    tp_create_library_item,
    tp_delete_library,
    tp_get_libraries,
    tp_get_library_item,
    tp_get_library_items,
    tp_schedule_library_workout,
    tp_update_library_item,
)
from tp_mcp.tools.metrics import tp_get_metrics, tp_get_nutrition, tp_log_metrics
from tp_mcp.tools.peaks import tp_get_peaks, tp_get_workout_prs
from tp_mcp.tools.profile import tp_get_profile, tp_list_athletes
from tp_mcp.tools.refresh_auth import tp_refresh_auth
from tp_mcp.tools.settings import (
    tp_get_athlete_settings,
    tp_get_pool_length_settings,
    tp_update_ftp,
    tp_update_hr_zones,
    tp_update_nutrition,
    tp_update_speed_zones,
)
from tp_mcp.tools.structure import tp_validate_structure
from tp_mcp.tools.weekly_summary import tp_get_weekly_summary
from tp_mcp.tools.workout_files import (
    tp_delete_workout_file,
    tp_download_workout_file,
    tp_upload_workout_file,
)
from tp_mcp.tools.workout_types import tp_get_workout_types
from tp_mcp.tools.workouts import (
    tp_add_workout_comment,
    tp_copy_workout,
    tp_create_workout,
    tp_delete_workout,
    tp_get_workout,
    tp_get_workout_comments,
    tp_get_workouts,
    tp_reorder_workouts,
    tp_update_workout,
)

__all__ = [
    "tp_add_workout_comment",
    "tp_analyze_workout",
    "tp_auth_status",
    "tp_copy_workout",
    "tp_create_availability",
    "tp_create_equipment",
    "tp_create_event",
    "tp_create_library",
    "tp_create_library_item",
    "tp_create_note",
    "tp_create_workout",
    "tp_delete_availability",
    "tp_delete_equipment",
    "tp_delete_event",
    "tp_delete_library",
    "tp_delete_note",
    "tp_delete_workout",
    "tp_delete_workout_file",
    "tp_download_workout_file",
    "tp_get_athlete_settings",
    "tp_get_atp",
    "tp_get_availability",
    "tp_get_equipment",
    "tp_get_events",
    "tp_get_fitness",
    "tp_get_focus_event",
    "tp_get_libraries",
    "tp_get_library_item",
    "tp_get_library_items",
    "tp_get_metrics",
    "tp_get_next_event",
    "tp_get_nutrition",
    "tp_get_peaks",
    "tp_get_pool_length_settings",
    "tp_get_profile",
    "tp_get_weekly_summary",
    "tp_get_workout",
    "tp_get_workout_comments",
    "tp_get_workout_prs",
    "tp_get_workout_types",
    "tp_list_athletes",
    "tp_get_workouts",
    "tp_log_metrics",
    "tp_refresh_auth",
    "tp_reorder_workouts",
    "tp_schedule_library_workout",
    "tp_update_equipment",
    "tp_update_event",
    "tp_update_ftp",
    "tp_update_hr_zones",
    "tp_update_library_item",
    "tp_update_nutrition",
    "tp_update_speed_zones",
    "tp_update_workout",
    "tp_upload_workout_file",
    "tp_validate_structure",
]
