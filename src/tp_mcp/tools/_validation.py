"""Pydantic input validation models for tool arguments."""

from datetime import date as date_type
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


def format_validation_error(exc: ValidationError) -> str:
    """Convert ValidationError to a clean user-facing message."""
    parts = []
    for err in exc.errors():
        field = " -> ".join(str(loc) for loc in err["loc"]) if err["loc"] else "input"
        parts.append(f"{field}: {err['msg']}")
    return "; ".join(parts)


class WorkoutIdInput(BaseModel):
    """Validates a workout ID is a positive integer."""

    workout_id: int = Field(gt=0)

    @field_validator("workout_id", mode="before")
    @classmethod
    def coerce_string(cls, v: object) -> object:
        if isinstance(v, str):
            return int(v)
        return v


class DateRangeInput(BaseModel):
    """Validates start/end date range for workout queries."""

    start_date: date_type
    end_date: date_type

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def coerce_string(cls, v: object) -> object:
        if isinstance(v, str):
            return date_type.fromisoformat(v)
        return v

    @model_validator(mode="after")
    def check_range(self) -> "DateRangeInput":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be before or equal to end_date")
        if (self.end_date - self.start_date).days > 90:
            raise ValueError("Date range too large. Maximum 90 days.")
        return self


class CreateWorkoutInput(BaseModel):
    """Validates input for workout creation."""

    date: date_type
    sport: str
    title: str = Field(min_length=1, max_length=200)
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    description: str | None = Field(default=None, max_length=2000)
    distance_km: float | None = Field(default=None, gt=0, le=1000)
    tss_planned: float | None = Field(default=None, gt=0, le=2000)
    structure: Any = None
    structured_workout: Any = None
    subtype_id: int | None = Field(default=None, gt=0)
    tags: str | None = Field(default=None, max_length=500)
    feeling: int | None = Field(default=None, ge=0, le=10)
    rpe: int | None = Field(default=None, ge=1, le=10)

    @field_validator("date", mode="before")
    @classmethod
    def coerce_date_string(cls, v: object) -> object:
        if isinstance(v, str):
            return date_type.fromisoformat(v)
        return v

    @field_validator("sport")
    @classmethod
    def check_sport(cls, v: str) -> str:
        from tp_mcp.tools.workouts import SPORT_TYPE_MAP

        if v not in SPORT_TYPE_MAP:
            valid = ", ".join(SPORT_TYPE_MAP.keys())
            raise ValueError(f"Invalid sport '{v}'. Valid: {valid}")
        return v

    @model_validator(mode="after")
    def check_duration_or_structure(self) -> "CreateWorkoutInput":
        if self.structure is not None and self.structured_workout is not None:
            raise ValueError("Provide only one of structure or structured_workout")
        if (
            self.duration_minutes is None
            and self.structure is None
            and self.structured_workout is None
        ):
            raise ValueError(
                "Either duration_minutes, structure, or structured_workout must be provided",
            )
        return self


class UpdateWorkoutInput(BaseModel):
    """Validates input for workout updates."""

    workout_id: int = Field(gt=0)
    sport: str | None = None
    subtype_id: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    date: date_type | None = None
    duration_minutes: float | None = Field(default=None, ge=0, le=1440)
    distance_km: float | None = Field(default=None, ge=0, le=1000)
    tss_planned: float | None = Field(default=None, ge=0, le=2000)
    tags: str | None = Field(default=None, max_length=500)
    athlete_comment: str | None = None
    coach_comment: str | None = None
    feeling: int | None = Field(default=None, ge=0, le=10)
    rpe: int | None = Field(default=None, ge=1, le=10)
    structure: Any = None
    structured_workout: Any = None

    @field_validator("workout_id", mode="before")
    @classmethod
    def coerce_id_string(cls, v: object) -> object:
        if isinstance(v, str):
            return int(v)
        return v

    @field_validator("date", mode="before")
    @classmethod
    def coerce_date_string(cls, v: object) -> object:
        if v is None:
            return v
        if isinstance(v, str):
            return date_type.fromisoformat(v)
        return v

    @field_validator("sport")
    @classmethod
    def check_sport(cls, v: str | None) -> str | None:
        if v is None:
            return v
        from tp_mcp.tools.workouts import SPORT_TYPE_MAP

        if v not in SPORT_TYPE_MAP:
            valid = ", ".join(SPORT_TYPE_MAP.keys())
            raise ValueError(f"Invalid sport '{v}'. Valid: {valid}")
        return v

    @model_validator(mode="after")
    def check_structure_inputs(self) -> "UpdateWorkoutInput":
        if self.structure is not None and self.structured_workout is not None:
            raise ValueError("Provide only one of structure or structured_workout")
        return self


class SingleDateInput(BaseModel):
    """Validates a single date input."""

    date: date_type

    @field_validator("date", mode="before")
    @classmethod
    def coerce_string(cls, v: object) -> object:
        if isinstance(v, str):
            return date_type.fromisoformat(v)
        return v


class FitnessInput(BaseModel):
    """Validates input for fitness queries."""

    days: int = Field(default=90, ge=1, le=365)
    start_date: date_type | None = None
    end_date: date_type | None = None

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def coerce_string(cls, v: object) -> object:
        if v is None:
            return v
        if isinstance(v, str):
            return date_type.fromisoformat(v)
        return v

    @model_validator(mode="after")
    def check_dates(self) -> "FitnessInput":
        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                raise ValueError("start_date must be before end_date")
        elif self.start_date or self.end_date:
            raise ValueError("Provide both start_date and end_date, or neither")
        return self


class PeaksInput(BaseModel):
    """Validates input for peaks queries."""

    sport: Literal["Bike", "Run"]
    pr_type: str
    days: int = Field(default=3650, ge=1, le=36500)

    @model_validator(mode="after")
    def check_pr_type(self) -> "PeaksInput":
        from tp_mcp.tools.peaks import BIKE_PR_TYPES, RUN_PR_TYPES

        valid = BIKE_PR_TYPES if self.sport == "Bike" else RUN_PR_TYPES
        if self.pr_type not in valid:
            raise ValueError(f"Invalid pr_type '{self.pr_type}' for {self.sport}. Valid: {', '.join(valid)}")
        return self
