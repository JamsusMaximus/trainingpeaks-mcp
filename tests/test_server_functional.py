"""Functional tests for the MCP server.

These tests call the server handlers directly (list_tools, call_tool)
to verify the full dispatch path works end-to-end, including argument
parsing, validation, and response formatting.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.server import call_tool, list_tools


def _parse_result(text_contents: list) -> dict:
    """Extract the JSON dict from a call_tool response."""
    assert len(text_contents) == 1
    return json.loads(text_contents[0].text)


# ---------------------------------------------------------------------------
# list_tools
# ---------------------------------------------------------------------------


class TestListTools:
    """Verify tool listing works and includes expected tools."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_all_tools(self):
        tools = await list_tools()
        names = {t.name for t in tools}
        # Core tools that must always exist
        core_tools = {
            "tp_auth_status",
            "tp_get_profile",
            "tp_get_workouts",
            "tp_get_workout",
            "tp_get_workout_prs",
            "tp_get_peaks",
            "tp_get_fitness",
            "tp_analyze_workout",
            "tp_create_workout",
            "tp_refresh_auth",
        }
        assert core_tools.issubset(names)
        # v2.0 tools
        v2_tools = {
            "tp_update_workout",
            "tp_delete_workout",
            "tp_copy_workout",
            "tp_reorder_workouts",
            "tp_get_workout_comments",
            "tp_add_workout_comment",
            "tp_validate_structure",
            "tp_get_workout_types",
            "tp_get_atp",
            "tp_get_weekly_summary",
            "tp_get_athlete_settings",
            "tp_update_ftp",
            "tp_update_hr_zones",
            "tp_update_speed_zones",
            "tp_update_nutrition",
            "tp_get_pool_length_settings",
            "tp_log_metrics",
            "tp_get_metrics",
            "tp_get_nutrition",
            "tp_get_equipment",
            "tp_create_equipment",
            "tp_update_equipment",
            "tp_delete_equipment",
            "tp_get_focus_event",
            "tp_get_next_event",
            "tp_get_events",
            "tp_create_event",
            "tp_update_event",
            "tp_delete_event",
            "tp_create_note",
            "tp_delete_note",
            "tp_get_availability",
            "tp_create_availability",
            "tp_delete_availability",
            "tp_get_libraries",
            "tp_get_library_items",
            "tp_get_library_item",
            "tp_create_library",
            "tp_delete_library",
            "tp_create_library_item",
            "tp_update_library_item",
            "tp_schedule_library_workout",
            "tp_list_athletes",
        }
        assert v2_tools.issubset(names)
        assert len(names) == len(core_tools) + len(v2_tools)

    @pytest.mark.asyncio
    async def test_create_workout_schema_includes_new_fields(self):
        """The tp_create_workout schema should advertise distance_km and tss_planned."""
        tools = await list_tools()
        cw = next(t for t in tools if t.name == "tp_create_workout")
        props = cw.inputSchema["properties"]
        assert "distance_km" in props
        assert "tss_planned" in props
        assert "distance_km" not in cw.inputSchema["required"]
        assert "tss_planned" not in cw.inputSchema["required"]


# ---------------------------------------------------------------------------
# call_tool: unknown tool
# ---------------------------------------------------------------------------


class TestUnknownTool:
    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        result = _parse_result(await call_tool("nonexistent_tool", {}))
        assert result["isError"] is True
        assert result["error_code"] == "UNKNOWN_TOOL"


# ---------------------------------------------------------------------------
# call_tool: tp_get_workouts  (validation only - no API)
# ---------------------------------------------------------------------------


class TestGetWorkoutsDispatch:
    """Test the server dispatch layer for tp_get_workouts."""

    @pytest.mark.asyncio
    async def test_invalid_date_format(self):
        result = _parse_result(await call_tool("tp_get_workouts", {"start_date": "nope", "end_date": "2025-01-01"}))
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_date_range_too_large(self):
        result = _parse_result(
            await call_tool("tp_get_workouts", {"start_date": "2025-01-01", "end_date": "2025-12-01"})
        )
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"
        assert "90" in result["message"]

    @pytest.mark.asyncio
    async def test_inverted_dates(self):
        result = _parse_result(
            await call_tool("tp_get_workouts", {"start_date": "2025-02-01", "end_date": "2025-01-01"})
        )
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_success_via_server(self, mock_api_responses):
        """Valid dates + mocked API should return workouts through the server layer."""
        workouts_response = APIResponse(success=True, data=mock_api_responses["workouts"])

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=workouts_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = _parse_result(
                await call_tool("tp_get_workouts", {"start_date": "2025-01-08", "end_date": "2025-01-09"})
            )

        assert result["count"] == 2
        assert len(result["workouts"]) == 2


# ---------------------------------------------------------------------------
# call_tool: tp_get_workout  (workout_id validation)
# ---------------------------------------------------------------------------


class TestGetWorkoutDispatch:
    """Test workout_id validation through server dispatch."""

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self):
        """workout_id like '../foo' must be rejected."""
        result = _parse_result(await call_tool("tp_get_workout", {"workout_id": "../etc/passwd"}))
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_negative_id_blocked(self):
        result = _parse_result(await call_tool("tp_get_workout", {"workout_id": "-1"}))
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_valid_id_reaches_api(self, mock_api_responses):
        workout_response = APIResponse(success=True, data=mock_api_responses["workout_detail"])

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=workout_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = _parse_result(await call_tool("tp_get_workout", {"workout_id": "1001"}))

        assert result["id"] == "1001"
        # Verify the URL used the validated integer, not the raw string
        call_args = mock_instance.get.call_args[0][0]
        assert "/workouts/1001" in call_args


# ---------------------------------------------------------------------------
# call_tool: tp_get_peaks  (validation)
# ---------------------------------------------------------------------------


class TestGetPeaksDispatch:
    @pytest.mark.asyncio
    async def test_invalid_pr_type(self):
        result = _parse_result(await call_tool("tp_get_peaks", {"sport": "Bike", "pr_type": "bogus"}))
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"
        assert "bogus" in result["message"]

    @pytest.mark.asyncio
    async def test_valid_pr_type(self):
        peaks_response = APIResponse(success=True, data=[])

        with patch("tp_mcp.tools.peaks.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=peaks_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = _parse_result(await call_tool("tp_get_peaks", {"sport": "Bike", "pr_type": "power20min"}))

        assert result["records"] == []
        assert result["sport"] == "Bike"


# ---------------------------------------------------------------------------
# call_tool: tp_get_fitness  (validation)
# ---------------------------------------------------------------------------


class TestGetFitnessDispatch:
    @pytest.mark.asyncio
    async def test_days_zero_rejected(self):
        result = _parse_result(await call_tool("tp_get_fitness", {"days": 0}))
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_days_over_365_rejected(self):
        result = _parse_result(await call_tool("tp_get_fitness", {"days": 500}))
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_start_without_end_rejected(self):
        result = _parse_result(await call_tool("tp_get_fitness", {"start_date": "2025-01-01"}))
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# call_tool: tp_analyze_workout  (workout_id validation)
# ---------------------------------------------------------------------------


class TestAnalyzeWorkoutDispatch:
    @pytest.mark.asyncio
    async def test_non_numeric_id_rejected(self):
        result = _parse_result(await call_tool("tp_analyze_workout", {"workout_id": "abc"}))
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# call_tool: tp_create_workout  (full dispatch including new fields)
# ---------------------------------------------------------------------------


class TestCreateWorkoutDispatch:
    """Functional tests for tp_create_workout through server dispatch."""

    @pytest.mark.asyncio
    async def test_invalid_sport_rejected(self):
        result = _parse_result(
            await call_tool(
                "tp_create_workout",
                {"date": "2026-01-10", "sport": "Hockey", "title": "Game", "duration_minutes": 60},
            )
        )
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_empty_title_rejected(self):
        result = _parse_result(
            await call_tool(
                "tp_create_workout",
                {"date": "2026-01-10", "sport": "Run", "title": "", "duration_minutes": 60},
            )
        )
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_duration_zero_rejected(self):
        result = _parse_result(
            await call_tool(
                "tp_create_workout",
                {"date": "2026-01-10", "sport": "Run", "title": "Test", "duration_minutes": 0},
            )
        )
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_title_too_long_rejected(self):
        result = _parse_result(
            await call_tool(
                "tp_create_workout",
                {"date": "2026-01-10", "sport": "Run", "title": "x" * 201, "duration_minutes": 60},
            )
        )
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_success_without_optional_fields(self):
        """Basic create without distance_km / tss_planned."""
        create_response = APIResponse(
            success=True,
            data={"workoutId": 9001, "title": "Easy Run", "workoutDay": "2026-01-10T00:00:00"},
        )

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=create_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = _parse_result(
                await call_tool(
                    "tp_create_workout",
                    {"date": "2026-01-10", "sport": "Run", "title": "Easy Run", "duration_minutes": 45},
                )
            )

        assert result["success"] is True
        assert result["workout_id"] == 9001
        payload = mock_instance.post.call_args[1]["json"]
        assert "distancePlanned" not in payload
        assert "tssPlanned" not in payload

    @pytest.mark.asyncio
    async def test_success_with_distance_and_tss(self):
        """Create with distance_km and tss_planned - verify they reach the API payload."""
        create_response = APIResponse(
            success=True,
            data={"workoutId": 9002, "title": "Long Ride", "workoutDay": "2026-02-01T00:00:00"},
        )

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=create_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = _parse_result(
                await call_tool(
                    "tp_create_workout",
                    {
                        "date": "2026-02-01",
                        "sport": "Bike",
                        "title": "Long Ride",
                        "duration_minutes": 240,
                        "description": "Endurance ride with tempo intervals",
                        "distance_km": 120.5,
                        "tss_planned": 280.0,
                    },
                )
            )

        assert result["success"] is True
        assert result["workout_id"] == 9002

        payload = mock_instance.post.call_args[1]["json"]
        assert payload["athleteId"] == 123
        assert payload["title"] == "Long Ride"
        assert payload["totalTimePlanned"] == 4.0  # 240 min -> 4 hours
        assert payload["distancePlanned"] == 120500.0  # 120.5 km -> metres
        assert payload["tssPlanned"] == 280.0
        assert payload["description"] == "Endurance ride with tempo intervals"
        assert payload["workoutDay"] == "2026-02-01T00:00:00"
        # Bike = (2, 2)
        assert payload["workoutTypeFamilyId"] == 2
        assert payload["workoutTypeValueId"] == 2

    @pytest.mark.asyncio
    async def test_negative_distance_rejected(self):
        result = _parse_result(
            await call_tool(
                "tp_create_workout",
                {
                    "date": "2026-01-10",
                    "sport": "Run",
                    "title": "Test",
                    "duration_minutes": 60,
                    "distance_km": -5,
                },
            )
        )
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_negative_tss_rejected(self):
        result = _parse_result(
            await call_tool(
                "tp_create_workout",
                {
                    "date": "2026-01-10",
                    "sport": "Run",
                    "title": "Test",
                    "duration_minutes": 60,
                    "tss_planned": -10,
                },
            )
        )
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# call_tool: catch-all error handler
# ---------------------------------------------------------------------------


class TestCatchAllErrorHandler:
    """Verify the server catch-all doesn't leak exception details."""

    @pytest.mark.asyncio
    async def test_internal_error_generic_message(self):
        """An unexpected exception should return generic message, not str(e)."""
        with patch("tp_mcp.server.tp_get_profile", side_effect=RuntimeError("secret db password")):
            result = _parse_result(await call_tool("tp_get_profile", {}))

        assert result["isError"] is True
        assert result["error_code"] == "API_ERROR"
        assert "secret" not in result["message"]
        assert "password" not in result["message"]
        assert "internal error" in result["message"].lower()
