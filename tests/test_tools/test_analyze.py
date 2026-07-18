"""Tests for workout analysis tool (v2 endpoints: summary/charts/laps)."""

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


def _sample_summary_response():
    """Minimal v2 summary response (shape confirmed live 2026-07)."""
    return {
        "startTimestamp": "2025-01-08T12:00:00",
        "data": {
            "TotalElapsedTime": {"friendlyName": "Elapsed time", "value": 3600, "unit": "h:m:s"},
            "TSS": {"friendlyName": "TSS", "value": 75.2},
            "NormalizedPower": {"friendlyName": "NP", "value": 220, "unit": "W"},
            "TotalDistance": {"friendlyName": "Distance", "value": 40.5, "unit": "km"},
        },
    }


def _sample_charts_response():
    """Minimal v2 charts response (shape confirmed live 2026-07)."""
    return {
        "metadata": {
            "Power": {
                "friendlyName": "Power", "unit": "watts",
                "minimum": 0, "maximum": 800, "average": 200,
                "zones": [
                    {"label": "1", "min": 0, "max": 150},
                    {"label": "2", "min": 151, "max": 200},
                ],
            },
            "HeartRate": {
                "friendlyName": "Heart Rate", "unit": "bpm",
                "minimum": 80, "maximum": 185, "average": 145,
            },
        },
        "data": [
            {"time": 0, "Power": 150, "HeartRate": 120},
            {"time": 4, "Power": 200, "HeartRate": 135},
            {"time": 8, "Power": 220, "HeartRate": 145},
        ],
    }


def _sample_laps_response():
    """Minimal v2 laps response (shape confirmed live 2026-07)."""
    return {
        "columnMetadata": {
            "Name": {"friendlyName": "Name", "type": "string"},
            "AveragePower": {"friendlyName": "Avg power", "unit": "W", "type": "number"},
        },
        "data": [
            {
                "id": 0, "Name": "Lap 1", "TotalElapsedTime": 1200,
                "AveragePower": 210, "AverageHeartRate": 142,
                "WorkoutStepIndex": 0, "Intensity": "Active", "LapTrigger": "Distance",
            },
        ],
        "lapDetectionState": {"powerIntervalsDetected": False},
        "lapSources": {"Device": 1},
    }


def _mock_post_sequence(status_summary=200, status_charts=200, status_laps=200):
    """Build an httpx.AsyncClient mock whose .post() side_effects the three
    v2 calls in call order (summary, charts, laps)."""
    def _resp(status, body):
        m = MagicMock()
        m.status_code = status
        m.json.return_value = body
        return m

    responses = [
        _resp(status_summary, _sample_summary_response()),
        _resp(status_charts, _sample_charts_response()),
        _resp(status_laps, _sample_laps_response()),
    ]
    mock_http_client = AsyncMock()
    mock_http_client.post.side_effect = responses
    return mock_http_client


class TestWorkoutAnalysisModel:
    """Tests for WorkoutAnalysis model (unchanged — merged v2 output still
    validates against the same shape)."""

    def test_parse_workout_analysis(self):
        data = {
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
                    "identifier": "Power", "name": "Power", "unit": "watts",
                    "min": 0, "max": 800, "average": 200,
                    "zones": [
                        {"label": "1", "min": 0, "max": 150},
                        {"label": "2", "min": 151, "max": 200},
                    ],
                },
                {
                    "identifier": "HeartRate", "name": "Heart Rate", "unit": "bpm",
                    "min": 80, "max": 185, "average": 145,
                },
            ],
            "data": [
                {"time": 0, "Power": 150, "HeartRate": 120},
                {"time": 4, "Power": 200, "HeartRate": 135},
                {"time": 8, "Power": 220, "HeartRate": 145},
            ],
            "lapData": [
                {"id": "1", "Name": "Lap 1", "TotalElapsedTime": "00:20:00",
                 "AveragePower": "210", "AverageHeartRate": "142"},
            ],
            "lapColumns": [
                {"identifier": "Name", "friendlyName": "Name", "type": "string"},
                {"identifier": "AveragePower", "friendlyName": "Avg power (W)", "type": "number"},
            ],
        }
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
        assert result.lap_columns[0]["identifier"] == "Name"

    def test_parse_minimal_analysis(self):
        data = {"workoutId": 123}
        result = parse_workout_analysis(data)
        assert result.workout_id == 123
        assert result.totals == []
        assert result.data_elements == []
        assert result.data == []


class TestTpAnalyzeWorkout:
    """Tests for tp_analyze_workout tool (v2: summary + charts + laps)."""

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

        with patch("tp_mcp.tools.analyze.TPClient") as mock_tp:
            mock_tp.return_value.__aenter__.return_value = mock_client
            with patch("tp_mcp.tools.analyze.httpx.AsyncClient") as mock_httpx:
                mock_http_client = _mock_post_sequence()
                mock_httpx.return_value.__aenter__.return_value = mock_http_client

                result = await tp_analyze_workout("3553733903")

        assert "isError" not in result or not result.get("isError")
        assert result["workoutId"] == 3553733903
        assert result["startTimestamp"] == "2025-01-08T12:00:00"
        # stopTimestamp derived from TotalElapsedTime=3600s (1h) — v2 summary
        # doesn't return it directly.
        assert result["stopTimestamp"] == "2025-01-08T13:00:00"
        assert "totals" in result
        assert "TSS" in result["totals"]
        assert result["totals"]["TSS"]["value"] == 75.2
        # Totals keyed by friendlyName ("NP"/"Distance"), not the v2 identifier
        # ("NormalizedPower"/"TotalDistance") — preserves the old v1 total names.
        assert "NP" in result["totals"]
        assert result["totals"]["NP"]["value"] == 220
        assert "Distance" in result["totals"]
        assert result["totals"]["Distance"]["value"] == 40.5
        assert len(result["dataChannels"]) == 2
        assert result["dataChannels"][0]["identifier"] == "Power"
        assert result["time_series_points"] == 3
        assert len(result["lapData"]) == 1
        assert result["lapData"][0]["Name"] == "Lap 1"
        assert "data_file" in result
        assert result["data_file"].endswith(".json")

        # Verify full merged data was saved to file
        saved = json.loads(Path(result["data_file"]).read_text())
        assert saved["data"][0]["Power"] == 150
        assert saved["lapData"][0]["Name"] == "Lap 1"

        # All three v2 endpoints were called, in order, with {"workoutId": ...}
        calls = mock_http_client.post.call_args_list
        assert len(calls) == 3
        assert calls[0].args[0].endswith("/workout-analysis/v2/analyze/summary")
        assert calls[1].args[0].endswith("/workout-analysis/v2/analyze/charts")
        assert calls[2].args[0].endswith("/workout-analysis/v2/analyze/laps")
        for c in calls:
            assert c.kwargs["json"] == {"workoutId": 3553733903}

    @pytest.mark.asyncio
    async def test_charts_and_laps_404_degrade_gracefully(self):
        """A workout with totals but no device file (e.g. manual entry) still
        returns a usable result — charts/laps 404 is soft, summary 404 is not."""
        mock_client = _mock_tp_client()

        with patch("tp_mcp.tools.analyze.TPClient") as mock_tp:
            mock_tp.return_value.__aenter__.return_value = mock_client
            with patch("tp_mcp.tools.analyze.httpx.AsyncClient") as mock_httpx:
                mock_http_client = _mock_post_sequence(status_charts=404, status_laps=404)
                mock_httpx.return_value.__aenter__.return_value = mock_http_client

                result = await tp_analyze_workout("3553733903")

        assert "isError" not in result or not result.get("isError")
        assert result["totals"]["TSS"]["value"] == 75.2
        assert result["dataChannels"] == []
        assert result["lapData"] == []
        assert result["time_series_points"] == 0

    @pytest.mark.asyncio
    async def test_401_expired_auth_on_summary(self):
        mock_client = _mock_tp_client()

        with patch("tp_mcp.tools.analyze.TPClient") as mock_tp:
            mock_tp.return_value.__aenter__.return_value = mock_client
            with patch("tp_mcp.tools.analyze.httpx.AsyncClient") as mock_httpx:
                mock_http_client = _mock_post_sequence(status_summary=401)
                mock_httpx.return_value.__aenter__.return_value = mock_http_client

                result = await tp_analyze_workout("12345")

        assert result["isError"] is True
        assert result["error_code"] == "AUTH_EXPIRED"
        # Auth failure short-circuits — charts/laps never called.
        assert mock_http_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_401_on_charts_is_hard_failure(self):
        """Unlike NOT_FOUND, an auth failure mid-sequence still propagates —
        it's a systemic problem, not a data-availability gap."""
        mock_client = _mock_tp_client()

        with patch("tp_mcp.tools.analyze.TPClient") as mock_tp:
            mock_tp.return_value.__aenter__.return_value = mock_client
            with patch("tp_mcp.tools.analyze.httpx.AsyncClient") as mock_httpx:
                mock_http_client = _mock_post_sequence(status_charts=401)
                mock_httpx.return_value.__aenter__.return_value = mock_http_client

                result = await tp_analyze_workout("12345")

        assert result["isError"] is True
        assert result["error_code"] == "AUTH_EXPIRED"

    @pytest.mark.asyncio
    async def test_404_not_found_on_summary(self):
        mock_client = _mock_tp_client()

        with patch("tp_mcp.tools.analyze.TPClient") as mock_tp:
            mock_tp.return_value.__aenter__.return_value = mock_client
            with patch("tp_mcp.tools.analyze.httpx.AsyncClient") as mock_httpx:
                mock_http_client = _mock_post_sequence(status_summary=404)
                mock_httpx.return_value.__aenter__.return_value = mock_http_client

                result = await tp_analyze_workout("9999")

        assert result["isError"] is True
        assert result["error_code"] == "NOT_FOUND"
        # summary is required — charts/laps never called.
        assert mock_http_client.post.call_count == 1

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
        """Verify the analysis API gets Bearer auth, not cookie auth, and no
        viewingPersonId (confirmed live: workoutId alone suffices, even for a
        coach viewing an athlete's workout)."""
        mock_client = _mock_tp_client()

        with patch("tp_mcp.tools.analyze.TPClient") as mock_tp:
            mock_tp.return_value.__aenter__.return_value = mock_client
            with patch("tp_mcp.tools.analyze.httpx.AsyncClient") as mock_httpx:
                mock_http_client = _mock_post_sequence()
                mock_httpx.return_value.__aenter__.return_value = mock_http_client

                await tp_analyze_workout("3553733903")

                call_kwargs = mock_http_client.post.call_args_list[0]
                headers = call_kwargs.kwargs["headers"]
                assert headers["Authorization"] == f"Bearer {TEST_ACCESS_TOKEN}"
                assert "Cookie" not in headers
                assert call_kwargs.kwargs["json"] == {"workoutId": 3553733903}
