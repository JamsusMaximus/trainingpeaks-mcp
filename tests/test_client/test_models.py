"""Tests for API response models."""

from datetime import date

from tp_mcp.client.models import (
    PeakData,
    UserProfile,
    WorkoutDetail,
    WorkoutSummary,
    parse_user_profile,
    parse_workout_detail,
    parse_workout_list,
)


class TestUserProfile:
    """Tests for UserProfile model."""

    def test_parse_user_profile(self):
        """Test parsing user profile from API response."""
        data = {
            "athleteId": 123,
            "userId": 456,
            "username": "test@example.com",
            "firstName": "John",
            "lastName": "Doe",
            "accountType": "premium",
        }
        profile = parse_user_profile(data)

        assert profile.athlete_id == 123
        assert profile.user_id == 456
        assert profile.email == "test@example.com"
        assert profile.first_name == "John"
        assert profile.last_name == "Doe"
        assert profile.name == "John Doe"
        assert profile.account_type == "premium"

    def test_parse_minimal_profile(self):
        """Test parsing profile with minimal fields."""
        data = {"athleteId": 123}
        profile = parse_user_profile(data)

        assert profile.athlete_id == 123
        assert profile.name == "Unknown"


class TestWorkoutSummary:
    """Tests for WorkoutSummary model."""

    def test_parse_completed_workout(self):
        """Test parsing completed workout summary."""
        data = {
            "workoutId": 1001,
            "workoutDay": "2025-01-08",
            "title": "Test Workout",
            "workoutTypeFamilyId": "bike",
            "totalTimePlanned": 3600,
            "totalTime": 3500,
            "tssPlanned": 80,
            "tssActual": 75,
            "completed": True,
        }
        workout = WorkoutSummary.model_validate(data)

        assert workout.id == 1001
        assert workout.workout_date == date(2025, 1, 8)
        assert workout.date == date(2025, 1, 8)  # property alias
        assert workout.title == "Test Workout"
        assert workout.is_completed is True
        assert workout.workout_status == "completed"

    def test_parse_planned_workout(self):
        """Test parsing planned workout summary."""
        data = {
            "workoutId": 1002,
            "workoutDay": "2025-01-09",
            "title": "Future Workout",
            "totalTimePlanned": 1800,
            "completed": False,
        }
        workout = WorkoutSummary.model_validate(data)

        assert workout.id == 1002
        assert workout.is_completed is False
        assert workout.workout_status == "planned"


class TestWorkoutDetail:
    """Tests for WorkoutDetail model."""

    def test_parse_workout_detail(self, mock_api_responses):
        """Test parsing full workout details."""
        workout = parse_workout_detail(mock_api_responses["workout_detail"])

        assert workout.id == 1001
        assert workout.date == date(2025, 1, 8)
        assert workout.title == "Test Workout"
        assert workout.avg_power == 200
        assert workout.normalized_power == 220
        assert workout.avg_hr == 145

    def test_parse_api_response_with_corrected_fields(self):
        """Test parsing API response with 'if' and 'normalizedPowerActual' fields.

        These field names differ from what you might expect:
        - 'if' (not 'intensityFactor') for actual intensity factor
        - 'normalizedPowerActual' (not 'normalizedPower') for NP
        """
        data = {
            "workoutId": 1003,
            "athleteId": 123,
            "title": "Interval Workout",
            "workoutTypeValueId": 2,
            "workoutDay": "2025-01-15T00:00:00",
            "startTime": "2025-01-15T18:30:00",
            "completed": None,
            "description": None,
            "coachComments": None,
            "distance": 30000.0,
            "distancePlanned": None,
            "totalTime": 1.0,
            "totalTimePlanned": 1.0,
            "heartRateAverage": 150,
            "calories": 570,
            "tssActual": 60.0,
            "tssPlanned": 65.0,
            "if": 0.78,
            "ifPlanned": 0.82,
            "normalizedPowerActual": 210.0,
            "powerAverage": 160,
            "elevationGain": 80.0,
            "cadenceAverage": 85,
        }
        workout = parse_workout_detail(data)

        assert workout.id == 1003
        assert workout.title == "Interval Workout"
        assert workout.tss_actual == 60.0
        assert workout.tss_planned == 65.0
        assert workout.if_actual == 0.78
        assert workout.if_planned == 0.82
        assert workout.normalized_power == 210.0
        assert workout.avg_power == 160
        assert workout.avg_hr == 150
        assert workout.avg_cadence == 85
        assert workout.elevation_gain == 80.0
        assert workout.calories == 570
        assert workout.distance_actual == 30000.0


class TestParseWorkoutList:
    """Tests for parse_workout_list function."""

    def test_parse_workout_list(self, mock_api_responses):
        """Test parsing list of workouts."""
        workouts = parse_workout_list(mock_api_responses["workouts"])

        assert len(workouts) == 2
        assert workouts[0].id == 1001
        assert workouts[0].is_completed is True
        assert workouts[1].id == 1002
        assert workouts[1].is_completed is False

    def test_parse_empty_list(self):
        """Test parsing empty workout list."""
        workouts = parse_workout_list([])
        assert len(workouts) == 0


class TestDateTimezoneStripping:
    """UTC datetime strings must not shift date via local-timezone conversion."""

    def test_workout_summary_utc_midnight(self):
        summary = WorkoutSummary.model_validate({
            "workoutId": 1,
            "workoutDay": "2024-03-24T00:00:00Z",
        })
        assert summary.workout_date == date(2024, 3, 24)

    def test_workout_summary_utc_with_offset(self):
        summary = WorkoutSummary.model_validate({
            "workoutId": 1,
            "workoutDay": "2024-03-24T00:00:00+00:00",
        })
        assert summary.workout_date == date(2024, 3, 24)

    def test_workout_summary_plain_date_unchanged(self):
        summary = WorkoutSummary.model_validate({
            "workoutId": 1,
            "workoutDay": "2024-03-24",
        })
        assert summary.workout_date == date(2024, 3, 24)

    def test_workout_detail_utc_midnight(self):
        detail = WorkoutDetail.model_validate({
            "workoutId": 1,
            "workoutDay": "2024-03-24T00:00:00Z",
        })
        assert detail.workout_date == date(2024, 3, 24)

    def test_peak_data_utc_midnight(self):
        peak = PeakData(
            duration="20m",
            duration_seconds=1200,
            value=300.0,
            peak_date="2024-03-24T00:00:00Z",
        )
        assert peak.peak_date == date(2024, 3, 24)
