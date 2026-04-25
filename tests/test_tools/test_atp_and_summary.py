"""Tests for ATP and weekly summary tools."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools.atp import tp_get_atp
from tp_mcp.tools.weekly_summary import _get_week_bounds, tp_get_weekly_summary


class TestGetATP:
    @pytest.mark.asyncio
    async def test_returns_weekly_data(self):
        data = [
            {"week": "2026-01-05", "volume": 400, "period": "Base 1 - Week 2",
             "raceName": "", "racePriority": "", "weeksToNextPriorityEvent": 12},
            {"week": "2026-01-12", "volume": 450, "period": "Base 1 - Week 3",
             "raceName": "Local 10K", "racePriority": "B", "weeksToNextPriorityEvent": 11},
        ]
        response = APIResponse(success=True, data=data)
        with patch("tp_mcp.tools.atp.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_atp("2026-01-01", "2026-03-01")

        assert result["count"] == 2
        assert result["weeks"][0]["period"] == "Base 1 - Week 2"
        assert result["weeks"][1]["race_name"] == "Local 10K"
        assert result["weeks"][1]["race_priority"] == "B"

    @pytest.mark.asyncio
    async def test_empty_range(self):
        response = APIResponse(success=True, data=[])
        with patch("tp_mcp.tools.atp.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_atp("2026-01-01", "2026-03-01")

        assert "No ATP data" in result.get("message", "")

    @pytest.mark.asyncio
    async def test_date_validation(self):
        """Start after end should fail."""
        result = await tp_get_atp("2026-03-01", "2026-01-01")
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"


class TestWeekBounds:
    def test_monday(self):
        from datetime import date

        monday, sunday = _get_week_bounds(date(2026, 3, 16))  # Monday
        assert monday.isoformat() == "2026-03-16"
        assert sunday.isoformat() == "2026-03-22"

    def test_wednesday(self):
        from datetime import date

        monday, sunday = _get_week_bounds(date(2026, 3, 18))  # Wednesday
        assert monday.isoformat() == "2026-03-16"
        assert sunday.isoformat() == "2026-03-22"

    def test_sunday(self):
        from datetime import date

        monday, sunday = _get_week_bounds(date(2026, 3, 22))  # Sunday
        assert monday.isoformat() == "2026-03-16"
        assert sunday.isoformat() == "2026-03-22"


class TestWeeklySummary:
    @pytest.mark.asyncio
    async def test_parallel_fetch(self):
        """Should fetch workouts and fitness in parallel."""
        with patch("tp_mcp.tools.weekly_summary.tp_get_workouts") as mock_workouts, \
             patch("tp_mcp.tools.weekly_summary.tp_get_fitness") as mock_fitness:

            mock_workouts.return_value = {
                "workouts": [
                    {"tss": 80, "duration_actual": 1.5, "duration_planned": 1.5},
                    {"tss": 60, "duration_actual": 1.0, "duration_planned": None},
                ],
                "count": 2,
            }
            mock_fitness.return_value = {
                "daily_data": [
                    {"date": "2026-03-22", "ctl": 65, "atl": 72, "tsb": -7},
                ],
            }

            result = await tp_get_weekly_summary("2026-03-18")

        assert result["workout_count"] == 2
        assert result["total_tss"] == 140.0
        assert result["total_duration_hours"] == 2.5
        assert result["fitness"]["ctl"] == 65

    @pytest.mark.asyncio
    async def test_default_current_week(self):
        """No date should default to current week."""
        with patch("tp_mcp.tools.weekly_summary.tp_get_workouts") as mock_workouts, \
             patch("tp_mcp.tools.weekly_summary.tp_get_fitness") as mock_fitness:

            mock_workouts.return_value = {"workouts": [], "count": 0}
            mock_fitness.return_value = {"daily_data": []}

            result = await tp_get_weekly_summary()

        assert "week" in result
        assert result["workout_count"] == 0
