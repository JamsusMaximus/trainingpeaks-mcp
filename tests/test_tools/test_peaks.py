"""Tests for peaks tools."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse, ErrorCode
from tp_mcp.tools.peaks import tp_get_peaks, tp_get_workout_prs


class TestTpGetPeaks:
    """Tests for tp_get_peaks tool."""

    @pytest.mark.asyncio
    async def test_get_peaks_success(self):
        """Test successful peaks retrieval."""
        user_response = APIResponse(success=True, data={"user": {"personId": 123}})
        peaks_response = APIResponse(
            success=True,
            data=[
                {
                    "rank": 1,
                    "value": 350,
                    "workoutId": 1001,
                    "workoutTitle": "Best Ride",
                    "workoutDate": "2025-01-05T00:00:00",
                },
                {
                    "rank": 2,
                    "value": 340,
                    "workoutId": 1002,
                    "workoutTitle": "Good Ride",
                    "workoutDate": "2025-01-03T00:00:00",
                },
                {
                    "rank": 3,
                    "value": 330,
                    "workoutId": 1003,
                    "workoutTitle": "OK Ride",
                    "workoutDate": "2025-01-01T00:00:00",
                },
            ],
        )

        with patch("tp_mcp.tools.peaks.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(side_effect=[user_response, peaks_response])
            mock_instance.athlete_id = None
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_peaks(sport="Bike", pr_type="power20min", days=365)

        assert "isError" not in result or not result.get("isError")
        assert result["sport"] == "Bike"
        assert result["pr_type"] == "power20min"
        assert len(result["records"]) == 3
        assert result["records"][0]["rank"] == 1
        assert result["records"][0]["value"] == 350

    @pytest.mark.asyncio
    async def test_get_peaks_invalid_pr_type(self):
        """Test peaks with invalid PR type."""
        result = await tp_get_peaks(sport="Bike", pr_type="invalid_type")

        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"
        assert "invalid_type" in result["message"]

    @pytest.mark.asyncio
    async def test_get_peaks_run_sport(self):
        """Test peaks for running sport."""
        user_response = APIResponse(success=True, data={"user": {"personId": 123}})
        peaks_response = APIResponse(
            success=True,
            data=[
                {
                    "rank": 1,
                    "value": 4.5,
                    "workoutId": 2001,
                    "workoutTitle": "Fast 5K",
                    "workoutDate": "2025-01-05T00:00:00",
                },
            ],
        )

        with patch("tp_mcp.tools.peaks.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(side_effect=[user_response, peaks_response])
            mock_instance.athlete_id = None
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_peaks(sport="Run", pr_type="speed5K", days=365)

        assert "isError" not in result or not result.get("isError")
        assert result["sport"] == "Run"
        assert result["pr_type"] == "speed5K"

    @pytest.mark.asyncio
    async def test_get_peaks_empty_data(self):
        """Test peaks with no records."""
        user_response = APIResponse(success=True, data={"user": {"personId": 123}})
        peaks_response = APIResponse(success=True, data=[])

        with patch("tp_mcp.tools.peaks.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(side_effect=[user_response, peaks_response])
            mock_instance.athlete_id = None
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_peaks(sport="Bike", pr_type="power5min", days=30)

        assert "isError" not in result or not result.get("isError")
        assert result["records"] == []


class TestTpGetWorkoutPrs:
    """Tests for tp_get_workout_prs tool."""

    @pytest.mark.asyncio
    async def test_get_workout_prs_success(self):
        """Test successful workout PRs retrieval."""
        user_response = APIResponse(success=True, data={"user": {"personId": 123}})
        prs_response = APIResponse(
            success=True,
            data={
                "personalRecordCount": 3,
                "personalRecords": [
                    {"class": "Power", "type": "power5sec", "value": 800, "rank": 1, "timeFrame": {"name": "5 sec"}},
                    {"class": "Power", "type": "power1min", "value": 400, "rank": 2, "timeFrame": {"name": "1 min"}},
                    {"class": "HeartRate", "type": "hR5min", "value": 180, "rank": 1, "timeFrame": {"name": "5 min"}},
                ],
            },
        )

        with patch("tp_mcp.tools.peaks.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(side_effect=[user_response, prs_response])
            mock_instance.athlete_id = None
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_workout_prs("1001")

        assert "isError" not in result or not result.get("isError")
        assert result["workout_id"] == "1001"
        assert result["personal_record_count"] == 3
        assert len(result["power_records"]) == 2
        assert len(result["heart_rate_records"]) == 1

    @pytest.mark.asyncio
    async def test_get_workout_prs_no_records(self):
        """Test workout PRs with no records."""
        user_response = APIResponse(success=True, data={"user": {"personId": 123}})
        prs_response = APIResponse(success=True, data=None)

        with patch("tp_mcp.tools.peaks.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(side_effect=[user_response, prs_response])
            mock_instance.athlete_id = None
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_workout_prs("9999")

        assert "isError" not in result or not result.get("isError")
        assert result["personal_record_count"] == 0
        assert result["records"] == []

    @pytest.mark.asyncio
    async def test_get_workout_prs_auth_error(self):
        """Test workout PRs with auth error."""
        user_response = APIResponse(
            success=False,
            error_code=ErrorCode.AUTH_INVALID,
            message="Auth failed",
        )

        with patch("tp_mcp.tools.peaks.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=user_response)
            mock_instance.athlete_id = None
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_workout_prs("1001")

        assert result["isError"] is True
        assert result["error_code"] == "AUTH_INVALID"
