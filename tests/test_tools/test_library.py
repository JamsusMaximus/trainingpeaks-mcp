"""Tests for workout library tools."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools.library import (
    tp_create_library,
    tp_create_library_item,
    tp_delete_library,
    tp_get_libraries,
    tp_get_library_items,
    tp_schedule_library_workout,
)


class TestGetLibraries:
    @pytest.mark.asyncio
    async def test_list_libraries(self):
        data = [
            {"exerciseLibraryId": 1, "libraryName": "My Workouts", "isDefaultContent": False, "ownerName": "Athlete"},
            {"exerciseLibraryId": 2, "libraryName": "Default", "isDefaultContent": True, "ownerName": "Joe Friel"},
        ]
        response = APIResponse(success=True, data=data)
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_libraries()

        assert result["count"] == 2
        assert result["libraries"][0]["name"] == "My Workouts"
        assert result["libraries"][0]["owner_name"] == "Athlete"
        assert result["libraries"][1]["is_default"] is True


class TestGetLibraryItems:
    @pytest.mark.asyncio
    async def test_list_items(self):
        data = [
            {
                "exerciseLibraryItemId": 10,
                "itemName": "Sweet Spot",
                "workoutTypeId": 2,
                "totalTimePlanned": 1.5,
                "tssPlanned": 80,
            },
        ]
        response = APIResponse(success=True, data=data)
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_library_items("1")

        assert result["count"] == 1
        assert result["items"][0]["name"] == "Sweet Spot"
        assert result["items"][0]["sport"] == 2


class TestCreateLibrary:
    @pytest.mark.asyncio
    async def test_create_sends_name(self):
        response = APIResponse(success=True, data={"exerciseLibraryId": 3})
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_library("Race Prep")

        assert result["success"] is True
        assert result["library_id"] == 3
        payload = mock_instance.post.call_args[1]["json"]
        assert payload["name"] == "Race Prep"


class TestDeleteLibrary:
    @pytest.mark.asyncio
    async def test_delete(self):
        response = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.delete = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_delete_library("1")

        assert result["success"] is True


class TestCreateLibraryItem:
    @pytest.mark.asyncio
    async def test_create_with_structure_nested_object(self):
        """Library item structure should be nested object, not string."""
        structure = {"structure": [{"type": "step"}]}
        response = APIResponse(success=True, data={"exerciseLibraryItemId": 20})
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_library_item(
                library_id="1", name="Tempo",
                sport_family_id=2, sport_type_id=3,
                structure=structure,
            )

        assert result["success"] is True
        payload = mock_instance.post.call_args[1]["json"]
        # Structure should be nested object, NOT JSON string
        assert isinstance(payload["structure"], dict)
        # Library API expects workoutTypeId/workoutSubTypeId; the fitness-API
        # field names silently create items with sport 0 (no power targets)
        assert payload["workoutTypeId"] == 2
        assert payload["workoutSubTypeId"] == 3
        assert "workoutTypeFamilyId" not in payload
        assert "workoutTypeValueId" not in payload


class TestScheduleLibraryWorkout:
    TEMPLATE = {
        "exerciseLibraryItemId": 10,
        "itemName": "Sweet Spot",
        "workoutTypeId": 2,
        "workoutSubTypeId": 3,
        "totalTimePlanned": 1.5,
        "tssPlanned": 80.0,
        "ifPlanned": 0.85,
        "description": "2x15 @ 88-93%",
        "structure": {"structure": [{"type": "step"}]},
    }

    @pytest.mark.asyncio
    async def test_schedule_copies_template_to_workout(self):
        items_response = APIResponse(success=True, data=[self.TEMPLATE])
        create_response = APIResponse(success=True, data={"workoutId": 999})
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=items_response)
            mock_instance.post = AsyncMock(return_value=create_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_schedule_library_workout("1", "10", "2026-04-01")

        assert result["success"] is True
        assert result["workout_id"] == 999
        # Copies the template into a planned workout (the native
        # addworkoutfromlibraryitem command endpoint returns HTTP 500)
        endpoint = mock_instance.post.call_args[0][0]
        assert endpoint == "/fitness/v6/athletes/123/workouts"
        payload = mock_instance.post.call_args[1]["json"]
        assert payload["workoutDay"] == "2026-04-01T00:00:00"
        assert payload["title"] == "Sweet Spot"
        assert payload["workoutTypeFamilyId"] == 2
        assert payload["workoutTypeValueId"] == 2
        assert payload["workoutSubTypeId"] == 3
        assert payload["tssPlanned"] == 80.0
        # Calendar workouts carry structure as a JSON string
        assert isinstance(payload["structure"], str)

    @pytest.mark.asyncio
    async def test_schedule_unknown_item_returns_not_found(self):
        items_response = APIResponse(success=True, data=[self.TEMPLATE])
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=items_response)
            mock_instance.post = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_schedule_library_workout("1", "404", "2026-04-01")

        assert result.get("isError") is True
        assert result["error_code"] == "NOT_FOUND"
        mock_instance.post.assert_not_called()
