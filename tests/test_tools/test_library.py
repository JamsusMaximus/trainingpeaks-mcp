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
            {"exerciseLibraryId": 1, "name": "My Workouts", "isDefault": False, "itemCount": 5},
            {"exerciseLibraryId": 2, "name": "Default", "isDefault": True, "itemCount": 20},
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
        assert result["libraries"][1]["is_default"] is True


class TestGetLibraryItems:
    @pytest.mark.asyncio
    async def test_list_items(self):
        data = [
            {"exerciseLibraryItemId": 10, "itemName": "Sweet Spot", "workoutTypeFamilyId": 2, "totalTimePlanned": 1.5, "tssPlanned": 80},
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


class TestScheduleLibraryWorkout:
    @pytest.mark.asyncio
    async def test_schedule_to_date(self):
        # No type info available (get returns error) → scheduling still works,
        # type repair is skipped.
        err = APIResponse(success=False, data=None)
        ok = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=err)
            mock_instance.post = AsyncMock(return_value=ok)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_schedule_library_workout("1", "10", "2026-04-01")

        assert result["success"] is True
        assert result["workout_type_set"] is False
        payload = mock_instance.post.call_args[1]["json"]
        assert payload["exerciseLibraryId"] == 1
        assert payload["exerciseLibraryItemId"] == 10
        assert payload["date"] == "2026-04-01T00:00:00"

    @pytest.mark.asyncio
    async def test_schedule_carries_template_sport(self):
        """The library item is Bike (2); the created workout comes out Other
        (100) → it must be updated to Bike."""
        items = APIResponse(
            success=True,
            data=[{"exerciseLibraryItemId": 10, "workoutTypeId": 2}],
        )
        post_ok = APIResponse(success=True, data=None)
        day_list = APIResponse(
            success=True,
            data=[{"workoutId": 555, "workoutTypeValueId": 100}],
        )
        workout_detail = APIResponse(
            success=True,
            data={"workoutId": 555, "workoutTypeValueId": 100, "title": "X"},
        )
        put_ok = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            # get order: library items → workouts-on-date → workout detail
            mock_instance.get = AsyncMock(
                side_effect=[items, day_list, workout_detail])
            mock_instance.post = AsyncMock(return_value=post_ok)
            mock_instance.put = AsyncMock(return_value=put_ok)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_schedule_library_workout("1", "10", "2026-04-01")

        assert result["success"] is True
        assert result["workout_type_set"] is True
        put_payload = mock_instance.put.call_args[1]["json"]
        assert put_payload["workoutTypeValueId"] == 2
        assert put_payload["workoutTypeFamilyId"] == 2

    @pytest.mark.asyncio
    async def test_schedule_leaves_correctly_typed_workout(self):
        """Already-typed workout (Bike) on that date is not touched."""
        items = APIResponse(
            success=True,
            data=[{"exerciseLibraryItemId": 10, "workoutTypeId": 2}],
        )
        post_ok = APIResponse(success=True, data=None)
        day_list = APIResponse(
            success=True,
            data=[{"workoutId": 555, "workoutTypeValueId": 2}],
        )
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(side_effect=[items, day_list])
            mock_instance.post = AsyncMock(return_value=post_ok)
            mock_instance.put = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_schedule_library_workout("1", "10", "2026-04-01")

        assert result["success"] is True
        assert result["workout_type_set"] is False
        mock_instance.put.assert_not_called()

    @pytest.mark.asyncio
    async def test_schedule_skips_ambiguous_day(self):
        """Multiple untyped workouts on the date and no library-item link →
        don't risk mutating the wrong one."""
        items = APIResponse(
            success=True,
            data=[{"exerciseLibraryItemId": 10, "workoutTypeId": 2}],
        )
        post_ok = APIResponse(success=True, data=None)
        day_list = APIResponse(
            success=True,
            data=[
                {"workoutId": 555, "workoutTypeValueId": 100},
                {"workoutId": 556, "workoutTypeValueId": 100},
            ],
        )
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(side_effect=[items, day_list])
            mock_instance.post = AsyncMock(return_value=post_ok)
            mock_instance.put = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_schedule_library_workout("1", "10", "2026-04-01")

        assert result["success"] is True
        assert result["workout_type_set"] is False
        mock_instance.put.assert_not_called()
