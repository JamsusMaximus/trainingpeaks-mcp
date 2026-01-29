"""Pydantic models for TrainingPeaks API responses.

These models extract only essential fields to minimize token consumption
when returned to AI assistants.
"""

from datetime import date as date_type
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UserProfile(BaseModel):
    """User profile information."""

    model_config = ConfigDict(populate_by_name=True)

    athlete_id: int = Field(alias="athleteId")
    user_id: int | None = Field(default=None, alias="userId")
    email: str | None = Field(default=None, alias="username")
    first_name: str | None = Field(default=None, alias="firstName")
    last_name: str | None = Field(default=None, alias="lastName")
    account_type: str | None = Field(default=None, alias="accountType")

    @property
    def name(self) -> str:
        """Get full name."""
        parts = [self.first_name, self.last_name]
        return " ".join(p for p in parts if p) or "Unknown"


class WorkoutSummary(BaseModel):
    """Summary of a workout (for list responses)."""

    model_config = ConfigDict(populate_by_name=True)

    id: int = Field(alias="workoutId")
    workout_date: date_type = Field(alias="workoutDay")
    title: str | None = None
    workout_type: str | int | None = Field(default=None, alias="workoutTypeValueId")
    sport: str | None = Field(default=None, alias="workoutTypeFamilyId")
    duration_planned: int | float | None = Field(default=None, alias="totalTimePlanned")
    duration_actual: int | float | None = Field(default=None, alias="totalTime")
    tss_planned: float | None = Field(default=None, alias="tssPlanned")
    tss_actual: float | None = Field(default=None, alias="tssActual")
    distance_planned: float | None = Field(default=None, alias="distancePlanned")
    distance_actual: float | None = Field(default=None, alias="distance")
    completed: bool | None = Field(default=None)
    description: str | None = None

    @property
    def date(self) -> date_type:
        """Alias for workout_date for backwards compatibility."""
        return self.workout_date

    @property
    def is_completed(self) -> bool:
        """Check if workout is completed."""
        return bool(self.completed) or self.duration_actual is not None

    @property
    def workout_status(self) -> str:
        """Get workout status as string."""
        return "completed" if self.is_completed else "planned"


class WorkoutInterval(BaseModel):
    """Single interval in a workout structure."""

    name: str | None = None
    duration: int | None = None  # seconds
    intensity_target: str | None = None
    power_low: int | None = None
    power_high: int | None = None
    hr_low: int | None = None
    hr_high: int | None = None
    cadence_low: int | None = None
    cadence_high: int | None = None
    notes: str | None = None


class WorkoutStructure(BaseModel):
    """Structured workout details."""

    warmup: list[WorkoutInterval] = Field(default_factory=list)
    main_set: list[WorkoutInterval] = Field(default_factory=list)
    cooldown: list[WorkoutInterval] = Field(default_factory=list)


class WorkoutDetail(BaseModel):
    """Full workout details."""

    model_config = ConfigDict(populate_by_name=True)

    id: int = Field(alias="workoutId")
    workout_date: date_type = Field(alias="workoutDay")
    title: str | None = None
    sport: str | None = Field(default=None, alias="workoutTypeFamilyId")
    workout_type: str | int | None = Field(default=None, alias="workoutTypeValueId")
    description: str | None = None
    coach_comments: str | None = Field(default=None, alias="coachComments")
    athlete_comments: str | None = Field(default=None, alias="athleteComments")
    duration_planned: int | float | None = Field(default=None, alias="totalTimePlanned")
    duration_actual: int | float | None = Field(default=None, alias="totalTime")
    tss_planned: float | None = Field(default=None, alias="tssPlanned")
    tss_actual: float | None = Field(default=None, alias="tssActual")
    if_planned: float | None = Field(default=None, alias="ifPlanned")
    if_actual: float | None = Field(default=None, alias="if")
    distance_planned: float | None = Field(default=None, alias="distancePlanned")
    distance_actual: float | None = Field(default=None, alias="distance")
    calories: int | None = None
    avg_power: float | None = Field(default=None, alias="powerAverage")
    normalized_power: float | None = Field(default=None, alias="normalizedPowerActual")
    avg_hr: int | None = Field(default=None, alias="heartRateAverage")
    avg_cadence: float | None = Field(default=None, alias="cadenceAverage")
    elevation_gain: float | None = Field(default=None, alias="elevationGain")
    completed: bool | None = Field(default=None)

    @property
    def date(self) -> date_type:
        """Alias for workout_date for backwards compatibility."""
        return self.workout_date


class PeakData(BaseModel):
    """Power or pace peak data point."""

    duration: str  # e.g., "5s", "1m", "5m", "20m", "60m"
    duration_seconds: int
    value: float  # watts for power, pace for running
    peak_date: date_type
    activity_id: int | None = None

    @property
    def date(self) -> date_type:
        """Alias for peak_date for backwards compatibility."""
        return self.peak_date


class PeaksResponse(BaseModel):
    """Response containing peak data."""

    peaks: list[PeakData]
    sport: str
    peak_type: str  # "power" or "pace"
    days: int


# Helper functions to parse API responses


def parse_user_profile(data: dict[str, Any]) -> UserProfile:
    """Parse user profile from API response."""
    return UserProfile.model_validate(data)


def parse_workout_summary(data: dict[str, Any]) -> WorkoutSummary:
    """Parse workout summary from API response."""
    return WorkoutSummary.model_validate(data)


def parse_workout_list(data: list[dict[str, Any]]) -> list[WorkoutSummary]:
    """Parse list of workout summaries."""
    return [parse_workout_summary(w) for w in data]


def parse_workout_detail(data: dict[str, Any]) -> WorkoutDetail:
    """Parse full workout details from API response."""
    return WorkoutDetail.model_validate(data)


def duration_to_string(seconds: int) -> str:
    """Convert seconds to human-readable duration string."""
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        minutes = seconds // 60
        return f"{minutes}m"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if minutes:
        return f"{hours}h{minutes}m"
    return f"{hours}h"


def parse_peak_duration(duration_str: str) -> int:
    """Parse duration string to seconds.

    Args:
        duration_str: Duration like "5s", "1m", "5m", "20m", "60m"

    Returns:
        Duration in seconds.
    """
    if duration_str.endswith("s"):
        return int(duration_str[:-1])
    if duration_str.endswith("m"):
        return int(duration_str[:-1]) * 60
    if duration_str.endswith("h"):
        return int(duration_str[:-1]) * 3600
    return int(duration_str)
