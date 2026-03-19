"""Tests for workout tools."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse, ErrorCode
from tp_mcp.tools.workouts import tp_create_workout, tp_get_workout, tp_get_workouts


class TestTpGetWorkouts:
    """Tests for tp_get_workouts tool."""

    @pytest.mark.asyncio
    async def test_get_workouts_success(self, mock_api_responses):
        """Test successful workout retrieval."""
        workouts_response = APIResponse(success=True, data=mock_api_responses["workouts"])

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=workouts_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_workouts("2025-01-08", "2025-01-09")

        assert "isError" not in result or not result.get("isError")
        assert result["count"] == 2
        assert len(result["workouts"]) == 2

    @pytest.mark.asyncio
    async def test_get_workouts_filter_completed(self, mock_api_responses):
        """Test filtering for completed workouts only."""
        workouts_response = APIResponse(success=True, data=mock_api_responses["workouts"])

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=workouts_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_workouts("2025-01-08", "2025-01-09", workout_filter="completed")

        assert result["count"] == 1
        assert result["workouts"][0]["type"] == "completed"

    @pytest.mark.asyncio
    async def test_get_workouts_invalid_dates(self):
        """Test with invalid date format."""
        result = await tp_get_workouts("invalid", "2025-01-09")

        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_get_workouts_date_order_error(self):
        """Test with start date after end date."""
        result = await tp_get_workouts("2025-01-10", "2025-01-09")

        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_get_workouts_date_range_too_large(self):
        """Test with date range exceeding 90 days."""
        result = await tp_get_workouts("2025-01-01", "2025-06-01")

        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"
        assert "90 days" in result["message"]

    @pytest.mark.asyncio
    async def test_get_workouts_date_range_at_limit(self, mock_api_responses):
        """Test with date range exactly at 90 days."""
        workouts_response = APIResponse(success=True, data=[])

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=workouts_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            # 90 days exactly should work
            result = await tp_get_workouts("2025-01-01", "2025-04-01")

        assert "isError" not in result or not result.get("isError")


class TestTpGetWorkout:
    """Tests for tp_get_workout tool."""

    @pytest.mark.asyncio
    async def test_get_workout_success(self, mock_api_responses):
        """Test successful single workout retrieval."""
        workout_response = APIResponse(success=True, data=mock_api_responses["workout_detail"])

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=workout_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_workout("1001")

        assert "isError" not in result or not result.get("isError")
        assert result["id"] == "1001"
        assert result["title"] == "Test Workout"
        assert result["metrics"]["avg_power"] == 200

    @pytest.mark.asyncio
    async def test_get_workout_not_found(self):
        """Test workout not found."""
        workout_response = APIResponse(
            success=False,
            error_code=ErrorCode.NOT_FOUND,
            message="Not found",
        )

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=workout_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_workout("9999")

        assert result["isError"] is True
        assert result["error_code"] == "NOT_FOUND"


class TestTpCreateWorkout:
    """Tests for tp_create_workout tool."""

    @pytest.mark.asyncio
    async def test_create_workout_success(self):
        """Test successful workout creation."""
        create_response = APIResponse(
            success=True,
            data={
                "workoutId": 5001,
                "title": "Morning Run",
                "workoutDay": "2026-01-10T00:00:00",
            },
        )

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=create_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_workout(
                date_str="2026-01-10",
                sport="Run",
                title="Morning Run",
                duration_minutes=60,
            )

        assert result["success"] is True
        assert result["workout_id"] == 5001

        # Verify post was called with correct endpoint and payload shape
        mock_instance.post.assert_called_once()
        call_args = mock_instance.post.call_args
        assert call_args[0][0] == "/fitness/v6/athletes/123/workouts"
        payload = call_args[1]["json"]
        assert payload["athleteId"] == 123
        assert payload["workoutDay"] == "2026-01-10T00:00:00"
        assert payload["workoutTypeFamilyId"] == 3
        assert payload["workoutTypeValueId"] == 3
        assert payload["title"] == "Morning Run"
        assert payload["totalTimePlanned"] == 1.0  # 60 min -> 1.0 hours

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "sport,expected_family,expected_value",
        [
            ("Swim", 1, 1),
            ("Bike", 2, 2),
            ("Run", 3, 3),
            ("Brick", 4, 4),
            ("Crosstrain", 5, 5),
            ("Walk", 6, 6),
            ("Strength", 7, 7),
            ("Rowing", 8, 8),
            ("XCSki", 9, 9),
            ("Other", 10, 10),
            ("Custom", 11, 11),
            ("DayOff", 12, 12),
            ("MtnBike", 13, 13),
        ],
    )
    async def test_create_workout_all_sport_types(self, sport, expected_family, expected_value):
        """Test that all sport types map to correct API IDs."""
        create_response = APIResponse(
            success=True,
            data={
                "workoutId": 6001,
                "title": f"Test {sport}",
                "workoutDay": "2026-03-01T00:00:00",
            },
        )

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=create_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_workout(
                date_str="2026-03-01",
                sport=sport,
                title=f"Test {sport}",
                duration_minutes=30,
            )

        assert result["success"] is True
        payload = mock_instance.post.call_args[1]["json"]
        assert payload["workoutTypeFamilyId"] == expected_family
        assert payload["workoutTypeValueId"] == expected_value

    @pytest.mark.asyncio
    async def test_create_workout_optional_fields(self):
        """Test that distance_km and tss_planned are passed to API when provided."""
        create_response = APIResponse(
            success=True,
            data={
                "workoutId": 5002,
                "title": "Long Ride",
                "workoutDay": "2026-02-01T00:00:00",
            },
        )

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=create_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_workout(
                date_str="2026-02-01",
                sport="Bike",
                title="Long Ride",
                duration_minutes=180,
                distance_km=100.5,
                tss_planned=250.0,
            )

        assert result["success"] is True
        payload = mock_instance.post.call_args[1]["json"]
        assert payload["distancePlanned"] == 100500.0  # 100.5 km -> metres
        assert payload["tssPlanned"] == 250.0

    @pytest.mark.asyncio
    async def test_create_workout_optional_fields_omitted(self):
        """Test that optional fields are not in payload when None."""
        create_response = APIResponse(
            success=True,
            data={
                "workoutId": 5003,
                "title": "Easy Run",
                "workoutDay": "2026-02-01T00:00:00",
            },
        )

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=create_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_workout(
                date_str="2026-02-01",
                sport="Run",
                title="Easy Run",
                duration_minutes=30,
            )

        assert result["success"] is True
        payload = mock_instance.post.call_args[1]["json"]
        assert "distancePlanned" not in payload
        assert "tssPlanned" not in payload

    @pytest.mark.asyncio
    @pytest.mark.parametrize("sport", ["Yoga", "Tennis", "bike", ""])
    async def test_create_workout_invalid_sport(self, sport):
        """Test that invalid sport types are rejected."""
        result = await tp_create_workout(
            date_str="2026-01-10",
            sport=sport,
            title="Test",
            duration_minutes=30,
        )

        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_create_workout_invalid_date(self):
        """Test with invalid date format."""
        result = await tp_create_workout(
            date_str="not-a-date",
            sport="Run",
            title="Test",
            duration_minutes=30,
        )

        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_create_workout_auth_failure(self):
        """Test when athlete ID cannot be retrieved."""
        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=None)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_workout(
                date_str="2026-01-10",
                sport="Run",
                title="Test",
                duration_minutes=30,
            )

        assert result["isError"] is True
        assert result["error_code"] == "AUTH_INVALID"

    @pytest.mark.asyncio
    async def test_create_workout_api_error(self):
        """Test when API returns an error."""
        error_response = APIResponse(
            success=False,
            error_code=ErrorCode.API_ERROR,
            message="API error: 400",
        )

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=error_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_workout(
                date_str="2026-01-10",
                sport="Bike",
                title="Test Ride",
                duration_minutes=60,
            )

        assert result["isError"] is True
        assert result["error_code"] == "API_ERROR"
        assert "details" not in result

    @pytest.mark.asyncio
    async def test_create_workout_unexpected_response(self):
        """Test when API returns unexpected data format."""
        unexpected_response = APIResponse(
            success=True,
            data=[{"unexpected": "format"}],
        )

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=unexpected_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_workout(
                date_str="2026-01-10",
                sport="Swim",
                title="Pool Session",
                duration_minutes=45,
            )

        assert result["isError"] is True
        assert result["error_code"] == "API_ERROR"
