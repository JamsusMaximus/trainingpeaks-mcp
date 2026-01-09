"""MCP tools for TrainingPeaks."""

from tp_mcp.tools.auth_status import tp_auth_status
from tp_mcp.tools.fitness import tp_get_fitness
from tp_mcp.tools.peaks import tp_get_peaks, tp_get_workout_prs
from tp_mcp.tools.profile import tp_get_profile
from tp_mcp.tools.refresh_auth import tp_refresh_auth
from tp_mcp.tools.workouts import tp_get_workout, tp_get_workouts

__all__ = [
    "tp_auth_status",
    "tp_get_fitness",
    "tp_get_peaks",
    "tp_get_profile",
    "tp_get_workout",
    "tp_get_workout_prs",
    "tp_get_workouts",
    "tp_refresh_auth",
]
