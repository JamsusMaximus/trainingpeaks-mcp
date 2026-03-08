"""Tests for Pydantic input validation models."""

import pytest
from pydantic import ValidationError

from tp_mcp.tools._validation import (
    CreateWorkoutInput,
    DateRangeInput,
    FitnessInput,
    PeaksInput,
    WorkoutIdInput,
    format_validation_error,
)


class TestWorkoutIdInput:
    """Tests for WorkoutIdInput validation."""

    def test_valid_int(self):
        result = WorkoutIdInput(workout_id=123)
        assert result.workout_id == 123

    def test_valid_string(self):
        result = WorkoutIdInput(workout_id="456")
        assert result.workout_id == 456

    def test_invalid_string(self):
        with pytest.raises(ValidationError):
            WorkoutIdInput(workout_id="abc")

    def test_zero(self):
        with pytest.raises(ValidationError):
            WorkoutIdInput(workout_id=0)

    def test_negative(self):
        with pytest.raises(ValidationError):
            WorkoutIdInput(workout_id=-1)


class TestDateRangeInput:
    """Tests for DateRangeInput validation."""

    def test_valid(self):
        result = DateRangeInput(start_date="2025-01-01", end_date="2025-01-31")
        assert result.start_date.isoformat() == "2025-01-01"
        assert result.end_date.isoformat() == "2025-01-31"

    def test_inverted(self):
        with pytest.raises(ValidationError, match="start_date must be before"):
            DateRangeInput(start_date="2025-02-01", end_date="2025-01-01")

    def test_over_90_days(self):
        with pytest.raises(ValidationError, match="90 days"):
            DateRangeInput(start_date="2025-01-01", end_date="2025-06-01")

    def test_at_90_days(self):
        result = DateRangeInput(start_date="2025-01-01", end_date="2025-04-01")
        assert result.start_date.isoformat() == "2025-01-01"

    def test_bad_date_string(self):
        with pytest.raises((ValidationError, ValueError)):
            DateRangeInput(start_date="not-a-date", end_date="2025-01-01")


class TestCreateWorkoutInput:
    """Tests for CreateWorkoutInput validation."""

    def test_valid(self):
        result = CreateWorkoutInput(
            date="2025-06-01",
            sport="Run",
            title="Morning Run",
            duration_minutes=60,
        )
        assert result.sport == "Run"
        assert result.duration_minutes == 60

    def test_empty_title(self):
        with pytest.raises(ValidationError):
            CreateWorkoutInput(date="2025-06-01", sport="Run", title="", duration_minutes=60)

    def test_title_too_long(self):
        with pytest.raises(ValidationError):
            CreateWorkoutInput(date="2025-06-01", sport="Run", title="x" * 201, duration_minutes=60)

    def test_duration_zero(self):
        with pytest.raises(ValidationError):
            CreateWorkoutInput(date="2025-06-01", sport="Run", title="Test", duration_minutes=0)

    def test_duration_too_large(self):
        with pytest.raises(ValidationError):
            CreateWorkoutInput(date="2025-06-01", sport="Run", title="Test", duration_minutes=1441)

    def test_bad_sport(self):
        with pytest.raises(ValidationError):
            CreateWorkoutInput(date="2025-06-01", sport="Hockey", title="Test", duration_minutes=60)

    def test_description_too_long(self):
        with pytest.raises(ValidationError):
            CreateWorkoutInput(
                date="2025-06-01",
                sport="Run",
                title="Test",
                duration_minutes=60,
                description="x" * 2001,
            )

    def test_distance_km_valid(self):
        result = CreateWorkoutInput(
            date="2025-06-01",
            sport="Bike",
            title="Ride",
            duration_minutes=120,
            distance_km=42.5,
        )
        assert result.distance_km == 42.5

    def test_distance_km_negative(self):
        with pytest.raises(ValidationError):
            CreateWorkoutInput(
                date="2025-06-01",
                sport="Bike",
                title="Ride",
                duration_minutes=60,
                distance_km=-1,
            )

    def test_distance_km_too_large(self):
        with pytest.raises(ValidationError):
            CreateWorkoutInput(
                date="2025-06-01",
                sport="Bike",
                title="Ride",
                duration_minutes=60,
                distance_km=1001,
            )

    def test_tss_planned_valid(self):
        result = CreateWorkoutInput(
            date="2025-06-01",
            sport="Run",
            title="Long Run",
            duration_minutes=90,
            tss_planned=150.5,
        )
        assert result.tss_planned == 150.5

    def test_tss_planned_negative(self):
        with pytest.raises(ValidationError):
            CreateWorkoutInput(
                date="2025-06-01",
                sport="Run",
                title="Run",
                duration_minutes=60,
                tss_planned=-10,
            )


class TestPeaksInput:
    """Tests for PeaksInput validation."""

    def test_valid_bike(self):
        result = PeaksInput(sport="Bike", pr_type="power20min")
        assert result.sport == "Bike"

    def test_valid_run(self):
        result = PeaksInput(sport="Run", pr_type="speed5K")
        assert result.sport == "Run"

    def test_invalid_pr_type(self):
        with pytest.raises(ValidationError, match="invalid_type"):
            PeaksInput(sport="Bike", pr_type="invalid_type")


class TestFitnessInput:
    """Tests for FitnessInput validation."""

    def test_days_only(self):
        result = FitnessInput(days=30)
        assert result.days == 30
        assert result.start_date is None

    def test_date_range(self):
        result = FitnessInput(start_date="2025-01-01", end_date="2025-03-01")
        assert result.start_date is not None
        assert result.end_date is not None

    def test_start_without_end(self):
        with pytest.raises(ValidationError, match="both"):
            FitnessInput(start_date="2025-01-01")

    def test_inverted_dates(self):
        with pytest.raises(ValidationError, match="before"):
            FitnessInput(start_date="2025-03-01", end_date="2025-01-01")

    def test_days_zero(self):
        with pytest.raises(ValidationError):
            FitnessInput(days=0)

    def test_days_too_large(self):
        with pytest.raises(ValidationError):
            FitnessInput(days=400)


class TestFormatValidationError:
    """Tests for format_validation_error helper."""

    def test_output_format(self):
        try:
            WorkoutIdInput(workout_id="abc")
        except ValidationError as e:
            msg = format_validation_error(e)
            assert "workout_id" in msg
