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
        user_response = APIResponse(
            success=True, data={"user": {"personId": 123}}
        )
        workouts_response = APIResponse(
            success=True, data=mock_api_responses["workouts"]
        )

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(
                side_effect=[user_response, workouts_response]
            )
            mock_instance.athlete_id = None
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_workouts("2025-01-08", "2025-01-09")

        assert "isError" not in result or not result.get("isError")
        assert result["count"] == 2
        assert len(result["workouts"]) == 2

    @pytest.mark.asyncio
    async def test_get_workouts_filter_completed(self, mock_api_responses):
        """Test filtering for completed workouts only."""
        user_response = APIResponse(
            success=True, data={"user": {"personId": 123}}
        )
        workouts_response = APIResponse(
            success=True, data=mock_api_responses["workouts"]
        )

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(
                side_effect=[user_response, workouts_response]
            )
            mock_instance.athlete_id = None
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_workouts(
                "2025-01-08", "2025-01-09", workout_filter="completed"
            )

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
        user_response = APIResponse(
            success=True, data={"user": {"personId": 123}}
        )
        workouts_response = APIResponse(success=True, data=[])

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(
                side_effect=[user_response, workouts_response]
            )
            mock_instance.athlete_id = None
            mock_client.return_value.__aenter__.return_value = mock_instance

            # 90 days exactly should work
            result = await tp_get_workouts("2025-01-01", "2025-04-01")

        assert "isError" not in result or not result.get("isError")


class TestTpGetWorkout:
    """Tests for tp_get_workout tool."""

    @pytest.mark.asyncio
    async def test_get_workout_success(self, mock_api_responses):
        """Test successful single workout retrieval."""
        user_response = APIResponse(
            success=True, data={"user": {"personId": 123}}
        )
        workout_response = APIResponse(
            success=True, data=mock_api_responses["workout_detail"]
        )

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(
                side_effect=[user_response, workout_response]
            )
            mock_instance.athlete_id = None
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_workout("1001")

        assert "isError" not in result or not result.get("isError")
        assert result["id"] == "1001"
        assert result["title"] == "Test Workout"
        assert result["metrics"]["avg_power"] == 200

    @pytest.mark.asyncio
    async def test_get_workout_not_found(self):
        """Test workout not found."""
        user_response = APIResponse(
            success=True, data={"user": {"personId": 123}}
        )
        workout_response = APIResponse(
            success=False,
            error_code=ErrorCode.NOT_FOUND,
            message="Not found",
        )

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(
                side_effect=[user_response, workout_response]
            )
            mock_instance.athlete_id = None
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_workout("9999")

        assert result["isError"] is True
        assert result["error_code"] == "NOT_FOUND"


class TestTpCreateWorkout:
    """Tests for tp_create_workout tool."""

    @pytest.mark.asyncio
    async def test_create_workout_posts_planned_fields(self):
        """Test that a planned workout is posted with TP field names and units."""
        created = APIResponse(success=True, data={"workoutId": 999})

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=created)
            mock_instance.athlete_id = None
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_workout(
                workout_date="2026-09-29",
                sport="run",
                title="Běh Z1",
                description="TF do 137",
                duration_minutes=45,
                distance_km=8,
                start_time="08:30",
                athlete_id=3980197,
            )

        endpoint, = mock_instance.post.call_args.args
        body = mock_instance.post.call_args.kwargs["json"]
        assert endpoint == "/fitness/v6/athletes/3980197/workouts"
        assert body["workoutTypeValueId"] == 3
        assert body["workoutDay"] == "2026-09-29T00:00:00"
        assert body["startTimePlanned"] == "2026-09-29T08:30:00"
        assert body["totalTimePlanned"] == 0.75
        assert body["distancePlanned"] == 8000
        assert body["description"] == "TF do 137"
        assert result == {"id": "999", "date": "2026-09-29", "title": "Běh Z1"}

    @pytest.mark.asyncio
    async def test_create_workout_invalid_sport(self):
        """Test with unknown sport."""
        result = await tp_create_workout(
            workout_date="2026-09-29", sport="yoga", title="x", athlete_id=1
        )

        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"
