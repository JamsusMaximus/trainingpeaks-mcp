"""Tests for health metrics tools."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools.metrics import tp_get_metrics, tp_get_nutrition, tp_log_metrics


class TestLogMetrics:
    @pytest.mark.asyncio
    async def test_log_single_metric(self):
        """Log weight only."""
        response = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.metrics.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_log_metrics(date="2026-03-01", weight_kg=75.5)

        assert result["success"] is True
        assert "weight_kg" in result["logged"]
        payload = mock_instance.post.call_args[1]["json"]
        assert payload["athleteId"] == 123
        assert len(payload["details"]) == 1
        assert payload["details"][0]["type"] == 9  # weight type ID
        assert payload["details"][0]["value"] == 75.5

    @pytest.mark.asyncio
    async def test_log_multiple_metrics(self):
        """Log multiple metrics in one request."""
        response = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.metrics.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_log_metrics(
                date="2026-03-01", weight_kg=75.5, hrv=45.0, sleep_hours=7.5,
            )

        assert result["success"] is True
        assert len(result["logged"]) == 3
        payload = mock_instance.post.call_args[1]["json"]
        assert len(payload["details"]) == 3

    @pytest.mark.asyncio
    async def test_log_no_metrics_rejected(self):
        result = await tp_log_metrics(date="2026-03-01")
        assert result["isError"] is True

    @pytest.mark.asyncio
    async def test_log_invalid_injury(self):
        """Injury value 0 should be rejected (min is 1)."""
        result = await tp_log_metrics(date="2026-03-01", injury=0)
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_metric_type_ids(self):
        """Verify metric type IDs match expected values."""
        from tp_mcp.tools.metrics import METRIC_TYPES

        assert METRIC_TYPES["pulse"]["type"] == 5
        assert METRIC_TYPES["weight_kg"]["type"] == 9
        assert METRIC_TYPES["sleep_hours"]["type"] == 6
        assert METRIC_TYPES["hrv"]["type"] == 60
        assert METRIC_TYPES["spo2"]["type"] == 53
        assert METRIC_TYPES["steps"]["type"] == 58


class TestGetMetrics:
    @pytest.mark.asyncio
    async def test_success(self):
        data = [{"date": "2026-03-01", "details": []}]
        response = APIResponse(success=True, data=data)
        with patch("tp_mcp.tools.metrics.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_metrics("2026-03-01", "2026-03-07")

        assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_empty_range(self):
        response = APIResponse(success=True, data=[])
        with patch("tp_mcp.tools.metrics.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_metrics("2026-03-01", "2026-03-07")

        assert "No metrics" in result.get("message", "")


class TestGetNutrition:
    @pytest.mark.asyncio
    async def test_success(self):
        response = APIResponse(success=True, data=[{"date": "2026-03-01"}])
        with patch("tp_mcp.tools.metrics.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_nutrition("2026-03-01", "2026-03-07")

        assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_empty(self):
        response = APIResponse(success=True, data=[])
        with patch("tp_mcp.tools.metrics.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_nutrition("2026-03-01", "2026-03-07")

        assert "No nutrition" in result.get("message", "")


class TestGetMetricsCompact:
    """compact=True flattens each day to {date, <snake_label>: value}; the default is unchanged."""

    def _days(self):
        def detail(label, mtype, value):
            return {
                "type": mtype, "label": label, "value": value, "time": "2026-03-01T06:10:00",
                "parentId": 42, "uploadClient": "Garmin Connect", "modifiedTime": None,
                "isPotentiallyNegative": False,
            }

        return [
            {
                "athleteId": 123, "id": "guid-1", "timeStamp": "2026-03-01T00:00:00",
                "details": [
                    detail("HRV", 60, 68), detail("Pulse", 5, 46), detail("Sleep", 6, 7.25),
                    detail("Time In Deep Sleep", 70, 1.1), detail("Time In REM Sleep", 72, 1.4),
                    detail("Body Battery", 74, 81), detail("Stress Level", 75, 24),
                    detail("Weight", 9, 74.2), detail("Blood Pressure", 11, [118, 76]),
                    detail("", 99, 3), detail("SPO2", 53, 97),
                ],
            },
            {
                "athleteId": 123, "id": "guid-2", "timeStamp": "2026-03-02T00:00:00",
                "details": [detail("HRV", 60, 71), detail("Weight", 9, 74.0), detail("Weight", 9, 73.8)],
            },
        ]

    async def _call(self, days, **kwargs):
        with patch("tp_mcp.tools.metrics.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=APIResponse(success=True, data=days))
            mock_client.return_value.__aenter__.return_value = mock_instance
            return await tp_get_metrics("2026-03-01", "2026-03-07", **kwargs)

    @pytest.mark.asyncio
    async def test_compact_rows_are_keyed_by_snake_cased_label(self):
        result = await self._call(self._days(), compact=True)

        assert result["compact"] is True
        assert result["count"] == 2
        day1, day2 = result["metrics"]
        assert day1 == {
            "date": "2026-03-01",
            "hrv": 68, "pulse": 46, "sleep_hours": 7.25,
            "time_in_deep_sleep": 1.1, "time_in_rem_sleep": 1.4,
            "body_battery": 81, "stress_level": 24, "weight": 74.2,
            "blood_pressure": [118, 76],  # list values pass through untouched
            "type_99": 3,  # empty label falls back to the type id
            "spo2": 97,
        }
        # No wrapper fields leak through.
        for key in ("parentId", "uploadClient", "modifiedTime", "type", "isPotentiallyNegative", "time"):
            assert key not in day1
        # Missing metrics are simply absent; a repeated label keeps the last value.
        assert day2 == {"date": "2026-03-02", "hrv": 71, "weight": 73.8}

    @pytest.mark.asyncio
    async def test_compact_reports_original_labels(self):
        result = await self._call(self._days(), compact=True)
        assert result["labels"]["sleep_hours"] == "Sleep"
        assert result["labels"]["time_in_deep_sleep"] == "Time In Deep Sleep"
        assert result["labels"]["hrv"] == "HRV"

    @pytest.mark.asyncio
    async def test_default_output_unchanged(self):
        days = self._days()
        result = await self._call(days)
        assert "compact" not in result
        assert "labels" not in result
        assert result["metrics"] == days
        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_compact_empty_range_keeps_message(self):
        result = await self._call([], compact=True)
        assert "No metrics" in result.get("message", "")

    def test_metric_column_derivation(self):
        from tp_mcp.tools.metrics import _metric_column

        assert _metric_column("HRV", 60) == "hrv"
        assert _metric_column("Time In REM Sleep", 72) == "time_in_rem_sleep"
        assert _metric_column("Sleep", 6) == "sleep_hours"
        assert _metric_column("Resting HR (bpm)", 5) == "resting_hr_bpm"
        assert _metric_column("3 km TT", 80) == "m_3_km_tt"
        assert _metric_column(None, 12) == "type_12"
