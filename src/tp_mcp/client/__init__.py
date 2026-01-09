"""HTTP client module for TrainingPeaks API."""

from tp_mcp.client.http import (
    APIError,
    APIResponse,
    AuthenticationError,
    ErrorCode,
    NotFoundError,
    RateLimitError,
    TPClient,
)
from tp_mcp.client.models import (
    PeakData,
    PeaksResponse,
    UserProfile,
    WorkoutDetail,
    WorkoutInterval,
    WorkoutStructure,
    WorkoutSummary,
    parse_user_profile,
    parse_workout_detail,
    parse_workout_list,
    parse_workout_summary,
)

__all__ = [
    "APIError",
    "APIResponse",
    "AuthenticationError",
    "ErrorCode",
    "NotFoundError",
    "PeakData",
    "PeaksResponse",
    "RateLimitError",
    "TPClient",
    "UserProfile",
    "WorkoutDetail",
    "WorkoutInterval",
    "WorkoutStructure",
    "WorkoutSummary",
    "parse_user_profile",
    "parse_workout_detail",
    "parse_workout_list",
    "parse_workout_summary",
]
