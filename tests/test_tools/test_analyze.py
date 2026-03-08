"""Tests for workout analysis tool."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.client.models import WorkoutAnalysis, parse_workout_analysis
from tp_mcp.tools.analyze import ANALYSIS_DATA_DIR, tp_analyze_workout

TEST_ATHLETE_ID = 123456
TEST_ACCESS_TOKEN = "gAAAA_test_access_token_12345"


def _mock_tp_client(athlete_id=TEST_ATHLETE_ID):
    """Create a mock TPClient with cached access token."""
    mock_client = AsyncMock()
    mock_client.ensure_athlete_id = AsyncMock(return_value=athlete_id)
    mock_client._ensure_access_token = AsyncMock(
        return_value=APIResponse(success=True)
    )

    mock_token_cache = MagicMock()
    mock_token_cache.access_token = TEST_ACCESS_TOKEN
    mock_client._token_cache = mock_token_cache

    return mock_client


def _sample_analysis_response():
    """Minimal analysis API response for testing (matches real API structure)."""
    return {
        "workoutId": 3553733903,
        "startTimestamp": "2025-01-08T12:00:00",
        "stopTimestamp": "2025-01-08T13:00:00",
        "totals": [
            {"name": "TSS", "value": "75.2"},
            {"name": "NP", "value": "220", "unit": "W"},
            {"name": "Distance", "value": "40.5", "unit": "km"},
        ],
        "dataElements": [
            {
                "identifier": "Power",
                "name": "Power",
                "unit": "watts",
                "min": 0,
                "max": 800,
                "average": 200,
                "sequence": 1,
                "enabled": True,
                "zones": [
                    {"label": "1", "min": 0, "max": 150},
                    {"label": "2", "min": 151, "max": 200},
                ],
                "zonesVisible": True,
            },
            {
                "identifier": "HeartRate",
                "name": "Heart Rate",
                "unit": "bpm",
                "min": 80,
                "max": 185,
                "average": 145,
                "sequence": 2,
                "enabled": True,
                "zonesVisible": True,
            },
        ],
        "data": [
            {"time": 0, "Power": 150, "HeartRate": 120},
            {"time": 4, "Power": 200, "HeartRate": 135},
            {"time": 8, "Power": 220, "HeartRate": 145},
        ],
        "lapData": [
            {
                "id": "1",
                "Name": "Lap 1",
                "TotalElapsedTime": "00:20:00",
                "AveragePower": "210",
                "AverageHeartRate": "142",
            },
        ],
        "lapColumns": [
            {"field": "Name", "headerName": "Name", "type": "string", "hidden": False},
            {"field": "AveragePower", "headerName": "Avg power (W)", "type": "number", "hidden": False},
        ],
        "lapsGridSettings": {"pinned": [], "detectIntervals": False},
        "state": {"intervalsDetected": False, "detectedIntervalCount": 0},
    }


class TestWorkoutAnalysisModel:
    """Tests for WorkoutAnalysis model."""

    def test_parse_workout_analysis(self):
        data = _sample_analysis_response()
        result = parse_workout_analysis(data)
        assert result.workout_id == 3553733903
        assert len(result.totals) == 3
        assert result.totals[0].name == "TSS"
        assert len(result.data_elements) == 2
        assert result.data_elements[0].identifier == "Power"
        assert len(result.data) == 3
        assert result.data[0]["Power"] == 150
        assert len(result.lap_data) == 1
        assert result.lap_data[0]["Name"] == "Lap 1"
        assert len(result.lap_columns) == 2
        assert result.lap_columns[0]["field"] == "Name"

    def test_parse_minimal_analysis(self):
        data = {"workoutId": 123}
        result = parse_workout_analysis(data)
        assert result.workout_id == 123
        assert result.totals == []
        assert result.data_elements == []
        assert result.data == []


class TestTpAnalyzeWorkout:
    """Tests for tp_analyze_workout tool."""

    @pytest.mark.asyncio
    async def test_invalid_workout_id(self):
        result = await tp_analyze_workout("abc")
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_no_athlete_id(self):
        mock_client = AsyncMock()
        mock_client.ensure_athlete_id = AsyncMock(return_value=None)

        with patch("tp_mcp.tools.analyze.TPClient") as mock_tp:
            mock_tp.return_value.__aenter__.return_value = mock_client
            result = await tp_analyze_workout("12345")

        assert result["isError"] is True
        assert result["error_code"] == "AUTH_INVALID"

    @pytest.mark.asyncio
    async def test_no_access_token(self):
        mock_client = AsyncMock()
        mock_client.ensure_athlete_id = AsyncMock(return_value=TEST_ATHLETE_ID)
        mock_client._ensure_access_token = AsyncMock(
            return_value=APIResponse(success=True)
        )

        mock_token_cache = MagicMock()
        mock_token_cache.access_token = None
        mock_client._token_cache = mock_token_cache

        with patch("tp_mcp.tools.analyze.TPClient") as mock_tp:
            mock_tp.return_value.__aenter__.return_value = mock_client
            result = await tp_analyze_workout("12345")

        assert result["isError"] is True
        assert result["error_code"] == "AUTH_INVALID"

    @pytest.mark.asyncio
    async def test_success(self):
        mock_client = _mock_tp_client()
        analysis_data = _sample_analysis_response()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = analysis_data

        with patch("tp_mcp.tools.analyze.TPClient") as mock_tp:
            mock_tp.return_value.__aenter__.return_value = mock_client
            with patch("tp_mcp.tools.analyze.httpx.AsyncClient") as mock_httpx:
                mock_http_client = AsyncMock()
                mock_http_client.post.return_value = mock_response
                mock_httpx.return_value.__aenter__.return_value = mock_http_client

                result = await tp_analyze_workout("3553733903")

        assert "isError" not in result or not result.get("isError")
        assert result["workoutId"] == 3553733903
        assert "totals" in result
        assert "TSS" in result["totals"]
        assert result["totals"]["TSS"]["value"] == "75.2"
        assert len(result["dataChannels"]) == 2
        assert result["dataChannels"][0]["identifier"] == "Power"
        assert result["time_series_points"] == 3
        assert "data_file" in result
        assert result["data_file"].endswith(".json")

        # Verify full data was saved to file
        saved = json.loads(Path(result["data_file"]).read_text())
        assert saved["data"] == analysis_data["data"]
        assert saved["data"][0]["Power"] == 150

    @pytest.mark.asyncio
    async def test_401_expired_auth(self):
        mock_client = _mock_tp_client()

        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("tp_mcp.tools.analyze.TPClient") as mock_tp:
            mock_tp.return_value.__aenter__.return_value = mock_client
            with patch("tp_mcp.tools.analyze.httpx.AsyncClient") as mock_httpx:
                mock_http_client = AsyncMock()
                mock_http_client.post.return_value = mock_response
                mock_httpx.return_value.__aenter__.return_value = mock_http_client

                result = await tp_analyze_workout("12345")

        assert result["isError"] is True
        assert result["error_code"] == "AUTH_EXPIRED"

    @pytest.mark.asyncio
    async def test_404_not_found(self):
        mock_client = _mock_tp_client()

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("tp_mcp.tools.analyze.TPClient") as mock_tp:
            mock_tp.return_value.__aenter__.return_value = mock_client
            with patch("tp_mcp.tools.analyze.httpx.AsyncClient") as mock_httpx:
                mock_http_client = AsyncMock()
                mock_http_client.post.return_value = mock_response
                mock_httpx.return_value.__aenter__.return_value = mock_http_client

                result = await tp_analyze_workout("9999")

        assert result["isError"] is True
        assert result["error_code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_timeout(self):
        mock_client = _mock_tp_client()

        with patch("tp_mcp.tools.analyze.TPClient") as mock_tp:
            mock_tp.return_value.__aenter__.return_value = mock_client
            with patch("tp_mcp.tools.analyze.httpx.AsyncClient") as mock_httpx:
                mock_http_client = AsyncMock()
                mock_http_client.post.side_effect = httpx.TimeoutException("timed out")
                mock_httpx.return_value.__aenter__.return_value = mock_http_client

                result = await tp_analyze_workout("12345")

        assert result["isError"] is True
        assert result["error_code"] == "NETWORK_ERROR"

    @pytest.mark.asyncio
    async def test_network_error(self):
        mock_client = _mock_tp_client()

        with patch("tp_mcp.tools.analyze.TPClient") as mock_tp:
            mock_tp.return_value.__aenter__.return_value = mock_client
            with patch("tp_mcp.tools.analyze.httpx.AsyncClient") as mock_httpx:
                mock_http_client = AsyncMock()
                mock_http_client.post.side_effect = httpx.ConnectError("refused")
                mock_httpx.return_value.__aenter__.return_value = mock_http_client

                result = await tp_analyze_workout("12345")

        assert result["isError"] is True
        assert result["error_code"] == "NETWORK_ERROR"

    @pytest.mark.asyncio
    async def test_sends_bearer_token_not_cookie(self):
        """Verify the analysis API gets Bearer auth, not cookie auth."""
        mock_client = _mock_tp_client()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _sample_analysis_response()

        with patch("tp_mcp.tools.analyze.TPClient") as mock_tp:
            mock_tp.return_value.__aenter__.return_value = mock_client
            with patch("tp_mcp.tools.analyze.httpx.AsyncClient") as mock_httpx:
                mock_http_client = AsyncMock()
                mock_http_client.post.return_value = mock_response
                mock_httpx.return_value.__aenter__.return_value = mock_http_client

                await tp_analyze_workout("3553733903")

                call_kwargs = mock_http_client.post.call_args
                headers = call_kwargs.kwargs["headers"]
                assert headers["Authorization"] == f"Bearer {TEST_ACCESS_TOKEN}"
                assert "Cookie" not in headers
                assert call_kwargs.kwargs["json"] == {
                    "workoutId": 3553733903,
                    "viewingPersonId": TEST_ATHLETE_ID,
                }
