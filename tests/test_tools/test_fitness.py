"""Tests for fitness tool."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse, ErrorCode
from tp_mcp.tools.fitness import tp_get_fitness


class TestTpGetFitness:
    """Tests for tp_get_fitness tool."""

    @pytest.mark.asyncio
    async def test_get_fitness_success(self):
        """Test successful fitness data retrieval."""
        user_response = APIResponse(success=True, data={"user": {"personId": 123}})
        fitness_response = APIResponse(
            success=True,
            data=[
                {"workoutDay": "2025-01-07T00:00:00", "tssActual": 50, "ctl": 45.2, "atl": 55.1, "tsb": -9.9},
                {"workoutDay": "2025-01-08T00:00:00", "tssActual": 80, "ctl": 46.0, "atl": 60.3, "tsb": -14.3},
                {"workoutDay": "2025-01-09T00:00:00", "tssActual": 0, "ctl": 45.5, "atl": 52.1, "tsb": -6.6},
            ],
        )

        with patch("tp_mcp.tools.fitness.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=user_response)
            mock_instance.post = AsyncMock(return_value=fitness_response)
            mock_instance.athlete_id = None
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_fitness(days=30)

        assert "isError" not in result or not result.get("isError")
        assert result["days"] == 30
        assert len(result["daily_data"]) == 3
        assert result["current"]["ctl"] == 45.5
        assert result["current"]["atl"] == 52.1
        assert result["current"]["tsb"] == -6.6
        assert "fitness_status" in result["current"]

    @pytest.mark.asyncio
    async def test_get_fitness_empty_data(self):
        """Test fitness retrieval with no data."""
        user_response = APIResponse(success=True, data={"user": {"personId": 123}})
        fitness_response = APIResponse(success=True, data=[])

        with patch("tp_mcp.tools.fitness.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=user_response)
            mock_instance.post = AsyncMock(return_value=fitness_response)
            mock_instance.athlete_id = None
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_fitness(days=30)

        assert "isError" not in result or not result.get("isError")
        assert result["data"] == []
        assert result["current"] is None

    @pytest.mark.asyncio
    async def test_get_fitness_invalid_days(self):
        """Test fitness with invalid days parameter."""
        result = await tp_get_fitness(days=0)
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

        result = await tp_get_fitness(days=400)
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_get_fitness_auth_error(self):
        """Test fitness retrieval with auth error."""
        user_response = APIResponse(
            success=False,
            error_code=ErrorCode.AUTH_INVALID,
            message="Auth failed",
        )

        with patch("tp_mcp.tools.fitness.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=user_response)
            mock_instance.athlete_id = None
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_fitness(days=30)

        assert result["isError"] is True
        assert result["error_code"] == "AUTH_INVALID"

    @pytest.mark.asyncio
    async def test_fitness_status_levels(self):
        """Test that fitness status is correctly assigned based on TSB."""
        from tp_mcp.tools.fitness import _get_fitness_status

        assert "Very Fresh" in _get_fitness_status(30)
        assert "Fresh" in _get_fitness_status(15)
        assert "Neutral" in _get_fitness_status(5)
        assert "Tired" in _get_fitness_status(-5)
        assert "Very Tired" in _get_fitness_status(-20)
        assert "Exhausted" in _get_fitness_status(-30)
