"""Tests for API response models."""

from datetime import date

from tp_mcp.client.models import (
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

    def test_parse_real_api_response(self):
        """Test parsing actual API response format from TrainingPeaks."""
        # Real API response format (from actual API call)
        data = {
            "workoutId": 3540909803,
            "athleteId": 6157627,
            "title": "PPO Interval (2/8) x 4",
            "workoutTypeValueId": 2,
            "workoutDay": "2026-01-29T00:00:00",
            "startTime": "2026-01-29T22:28:29",
            "completed": None,
            "description": None,
            "coachComments": None,
            "distance": 31239.130859375,
            "distancePlanned": None,
            "totalTime": 1.0086110830307007,
            "totalTimePlanned": 1.0,
            "heartRateAverage": 150,
            "calories": 572,
            "tssActual": 59.75,
            "tssPlanned": 66.7,
            "if": 0.77923333164699449,
            "ifPlanned": 0.82,
            "normalizedPowerActual": 213.0,
            "powerAverage": 161,
            "elevationGain": 81.0,
            "cadenceAverage": 83,
        }
        workout = parse_workout_detail(data)

        assert workout.id == 3540909803
        assert workout.title == "PPO Interval (2/8) x 4"
        assert workout.tss_actual == 59.75
        assert workout.tss_planned == 66.7
        assert workout.if_actual == 0.77923333164699449
        assert workout.if_planned == 0.82
        assert workout.normalized_power == 213.0
        assert workout.avg_power == 161
        assert workout.avg_hr == 150
        assert workout.avg_cadence == 83
        assert workout.elevation_gain == 81.0
        assert workout.calories == 572
        assert workout.distance_actual == 31239.130859375


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
