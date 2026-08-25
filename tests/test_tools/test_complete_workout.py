"""Tests for tp_complete_workout.

The fixtures mirror a real captured request/response pair from the
TrainingPeaks iPhone app (a 5-minute "Diver's Apnea" breathing session).
The app marks a workout complete by writing ``totalTime`` and nothing
else -- it sends no ``completed`` flag at all -- and the server derives
compliance and calories in the response.
"""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools.workouts import tp_complete_workout

FIVE_MINUTES_IN_HOURS = 0.08333333333333333


def _planned_workout(**overrides):
    """A planned workout as returned by GET, shaped like the real capture."""
    workout = {
        "workoutId": 1001,
        "athleteId": 123,
        "title": "Diver's Apnea",
        "workoutDay": "2026-08-20T00:00:00",
        "workoutTypeValueId": 100,
        "totalTimePlanned": FIVE_MINUTES_IN_HOURS,
        "totalTime": None,
        "distancePlanned": None,
        "distance": None,
        "tssPlanned": None,
        "tssActual": None,
        "completed": None,
        "structure": None,
        "description": "5 min of breathing",
        "orderOnDay": 3,
    }
    workout.update(overrides)
    return workout


def _mock_client(existing, put_data=None):
    """Patch TPClient so GET returns `existing` and PUT returns `put_data`."""
    mock_instance = AsyncMock()
    mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
    mock_instance.get = AsyncMock(return_value=APIResponse(success=True, data=existing))
    mock_instance.put = AsyncMock(return_value=APIResponse(success=True, data=put_data))
    return mock_instance


class TestCompleteWorkoutDefaults:
    """Completing with no metrics copies the plan across."""

    @pytest.mark.asyncio
    async def test_copies_planned_duration_to_actual(self):
        """The captured behaviour: totalTime is set from totalTimePlanned."""
        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = _mock_client(_planned_workout())
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_complete_workout(workout_id="1001")

        assert result["success"] is True
        payload = mock_instance.put.call_args[1]["json"]
        assert payload["totalTime"] == FIVE_MINUTES_IN_HOURS
        assert payload["totalTime"] == payload["totalTimePlanned"]

    @pytest.mark.asyncio
    async def test_does_not_set_a_completed_flag(self):
        """TrainingPeaks derives completion from actuals, not a boolean."""
        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = _mock_client(_planned_workout())
            mock_client.return_value.__aenter__.return_value = mock_instance

            await tp_complete_workout(workout_id="1001")

        payload = mock_instance.put.call_args[1]["json"]
        assert payload["completed"] is None

    @pytest.mark.asyncio
    async def test_copies_planned_tss_and_distance(self):
        """Planned load carries over so the session still counts toward CTL/ATL."""
        existing = _planned_workout(tssPlanned=85.0, distancePlanned=42000.0)
        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = _mock_client(existing)
            mock_client.return_value.__aenter__.return_value = mock_instance

            await tp_complete_workout(workout_id="1001")

        payload = mock_instance.put.call_args[1]["json"]
        assert payload["tssActual"] == 85.0
        assert payload["distance"] == 42000.0

    @pytest.mark.asyncio
    async def test_preserves_unrelated_fields(self):
        """Merging into the full GET must not drop anything else."""
        existing = _planned_workout(structure='{"steps": []}', orderOnDay=3)
        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = _mock_client(existing)
            mock_client.return_value.__aenter__.return_value = mock_instance

            await tp_complete_workout(workout_id="1001")

        payload = mock_instance.put.call_args[1]["json"]
        assert payload["structure"] == '{"steps": []}'
        assert payload["description"] == "5 min of breathing"
        assert payload["orderOnDay"] == 3
        assert payload["title"] == "Diver's Apnea"


class TestCompleteWorkoutOverrides:
    """Explicit metrics win over the planned values."""

    @pytest.mark.asyncio
    async def test_explicit_duration_overrides_plan(self):
        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = _mock_client(_planned_workout())
            mock_client.return_value.__aenter__.return_value = mock_instance

            await tp_complete_workout(workout_id="1001", duration_minutes=12)

        payload = mock_instance.put.call_args[1]["json"]
        assert payload["totalTime"] == pytest.approx(0.2)
        assert payload["totalTimePlanned"] == FIVE_MINUTES_IN_HOURS

    @pytest.mark.asyncio
    async def test_explicit_distance_and_tss_override_plan(self):
        existing = _planned_workout(tssPlanned=85.0, distancePlanned=42000.0)
        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = _mock_client(existing)
            mock_client.return_value.__aenter__.return_value = mock_instance

            await tp_complete_workout(workout_id="1001", distance_km=38.5, tss=91)

        payload = mock_instance.put.call_args[1]["json"]
        assert payload["distance"] == 38500
        assert payload["tssActual"] == 91

    @pytest.mark.asyncio
    async def test_subjective_metrics_recorded(self):
        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = _mock_client(_planned_workout())
            mock_client.return_value.__aenter__.return_value = mock_instance

            await tp_complete_workout(workout_id="1001", rpe=6, feeling=8, calories=120)

        payload = mock_instance.put.call_args[1]["json"]
        assert payload["rpe"] == 6
        assert payload["feeling"] == 8
        assert payload["calories"] == 120

    @pytest.mark.asyncio
    async def test_calories_left_to_server_when_omitted(self):
        """The server computes calories; we must not send a made-up value."""
        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = _mock_client(_planned_workout())
            mock_client.return_value.__aenter__.return_value = mock_instance

            await tp_complete_workout(workout_id="1001")

        payload = mock_instance.put.call_args[1]["json"]
        assert payload.get("calories") is None


class TestCompleteWorkoutResponse:
    """Server-derived values are surfaced back to the caller."""

    @pytest.mark.asyncio
    async def test_returns_server_computed_compliance_and_calories(self):
        put_data = {
            "workoutId": 1001,
            "title": "Diver's Apnea",
            "totalTime": FIVE_MINUTES_IN_HOURS,
            "completed": None,
            "complianceDurationPercent": 100.0,
            "calories": 42,
        }
        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = _mock_client(_planned_workout(), put_data=put_data)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_complete_workout(workout_id="1001")

        assert result["success"] is True
        assert result["duration_minutes"] == pytest.approx(5.0)
        assert result["calories"] == 42
        assert result["compliance_duration_percent"] == 100.0
        assert result["title"] == "Diver's Apnea"


class TestCompleteWorkoutErrors:
    """Failure paths."""

    @pytest.mark.asyncio
    async def test_no_planned_duration_is_an_error(self):
        """Nothing to complete with, and silently inventing a duration is wrong."""
        existing = _planned_workout(totalTimePlanned=None)
        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = _mock_client(existing)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_complete_workout(workout_id="1001")

        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"
        assert "duration_minutes" in result["message"]
        mock_instance.put.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_planned_duration_recovers_with_explicit_duration(self):
        existing = _planned_workout(totalTimePlanned=None)
        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = _mock_client(existing)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_complete_workout(workout_id="1001", duration_minutes=30)

        assert result["success"] is True
        payload = mock_instance.put.call_args[1]["json"]
        assert payload["totalTime"] == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_invalid_workout_id_rejected(self):
        result = await tp_complete_workout(workout_id="0")
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_out_of_range_rpe_rejected(self):
        result = await tp_complete_workout(workout_id="1001", rpe=42)
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_get_failure_surfaces(self):
        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(
                return_value=APIResponse(success=False, message="Workout not found"),
            )
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_complete_workout(workout_id="1001")

        assert result["isError"] is True
        mock_instance.put.assert_not_called()

    @pytest.mark.asyncio
    async def test_put_failure_surfaces(self):
        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = _mock_client(_planned_workout())
            mock_instance.put = AsyncMock(
                return_value=APIResponse(success=False, message="Conflict"),
            )
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_complete_workout(workout_id="1001")

        assert result["isError"] is True
        assert "Conflict" in result["message"]
