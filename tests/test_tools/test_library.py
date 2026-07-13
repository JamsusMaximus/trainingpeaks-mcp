"""Tests for workout library tools."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.context import athlete_override
from tp_mcp.client.http import APIResponse
from tp_mcp.tools.library import (
    tp_create_library,
    tp_create_library_item,
    tp_delete_library,
    tp_get_libraries,
    tp_get_library_items,
    tp_schedule_library_workout,
    tp_update_library_item,
)


class TestGetLibraries:
    @pytest.mark.asyncio
    async def test_list_libraries(self):
        data = [
            {"exerciseLibraryId": 1, "libraryName": "My Workouts", "isDefaultContent": False,
             "ownerName": "Athlete", "ownerId": 7, "itemCount": 5},
            {"exerciseLibraryId": 2, "libraryName": "Default", "isDefaultContent": True,
             "ownerName": "Joe Friel", "ownerId": 7},
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
        assert result["libraries"][0]["owner_id"] == 7
        assert result["libraries"][0]["item_count"] == 5
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
            mock_instance._get_user_data = AsyncMock(return_value={"personId": 999})
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_library("Race Prep")

        assert result["success"] is True
        assert result["library_id"] == 3
        payload = mock_instance.post.call_args[1]["json"]
        assert payload["libraryName"] == "Race Prep"
        assert payload["ownerId"] == 999


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

    @pytest.mark.asyncio
    async def test_create_backfills_polyline_and_range(self):
        """A native structure without preview fields gets polyline +
        primaryIntensityTargetOrRange so TP renders the thumbnail."""
        def _block(begin, end, dur, lo, hi, cls):
            return {
                "type": "step", "length": {"value": 1, "unit": "repetition"},
                "begin": begin, "end": end,
                "steps": [{
                    "name": cls, "length": {"value": dur, "unit": "second"},
                    "targets": [{"minValue": lo, "maxValue": hi}],
                    "intensityClass": cls,
                }],
            }
        structure = {
            "primaryIntensityMetric": "percentOfFtp",
            "primaryLengthMetric": "duration",
            "structure": [
                _block(0, 300, 300, 50, 60, "warmUp"),
                _block(300, 3300, 3000, 65, 72, "active"),
                _block(3300, 3600, 300, 50, 55, "coolDown"),
            ],
        }
        response = APIResponse(success=True, data={"exerciseLibraryItemId": 21})
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_library_item(
                library_id="1", name="Endurance",
                sport_family_id=2, sport_type_id=2, structure=structure,
            )

        assert result["success"] is True
        st = mock_instance.post.call_args[1]["json"]["structure"]
        assert st["primaryIntensityTargetOrRange"] == "range"
        # 3 single-step blocks → 3 bars × 4 points
        assert len(st["polyline"]) == 12
        # normalised so the structure's peak target (active 72) = 1.0;
        # warm-up 60 → 60/72 = 0.8333. Nothing exceeds 1.0.
        assert [0.0833, 1.0] in st["polyline"]
        assert [0.0, 0.8333] in st["polyline"]
        assert all(p[1] <= 1.0 for p in st["polyline"])


class TestStructurePreviewHelper:
    def test_polyline_expands_repetition_and_normalises(self):
        from tp_mcp.tools.library import _compute_native_polyline
        blocks = [
            {"type": "step", "length": {"value": 1, "unit": "repetition"},
             "steps": [{"length": {"value": 2000, "unit": "meter"},
                        "targets": [{"minValue": 70, "maxValue": 80}]}]},
            {"type": "repetition", "length": {"value": 6, "unit": "repetition"},
             "steps": [
                 {"length": {"value": 800, "unit": "meter"},
                  "targets": [{"minValue": 102, "maxValue": 104}]},
                 {"length": {"value": 400, "unit": "meter"},
                  "targets": [{"minValue": 70, "maxValue": 75}]},
             ]},
        ]
        poly = _compute_native_polyline(blocks)
        # warmup bar + 6×(work+rest) bars = 13 bars × 4 points
        assert len(poly) == 13 * 4
        # normalised: the peak target (work 104) = 1.0 and nothing exceeds it
        assert any(pt[1] == 1.0 for pt in poly)
        assert all(pt[1] <= 1.0 for pt in poly)

    def test_polyline_absolute_targets_stay_in_unit_range(self):
        """Absolute watts must normalise to [0,1], not the old /100 (300 W → 3.0)."""
        from tp_mcp.tools.library import _compute_native_polyline
        blocks = [
            {"type": "step", "length": {"value": 1, "unit": "repetition"},
             "steps": [{"length": {"value": 600, "unit": "second"},
                        "targets": [{"minValue": 150, "maxValue": 150}]}]},
            {"type": "step", "length": {"value": 1, "unit": "repetition"},
             "steps": [{"length": {"value": 300, "unit": "second"},
                        "targets": [{"minValue": 300, "maxValue": 300}]}]},
        ]
        poly = _compute_native_polyline(blocks)
        assert max(p[1] for p in poly) == 1.0    # 300 W peak → 1.0, not 3.0
        assert any(p[1] == 0.5 for p in poly)     # 150 W → 150/300

    def test_polyline_uses_minvalue_when_no_max(self):
        """A floor-only target (`{"minValue": 55}`) is a real bar, not height 0."""
        from tp_mcp.tools.library import _compute_native_polyline
        blocks = [
            {"type": "step", "length": {"value": 1, "unit": "repetition"},
             "steps": [{"length": {"value": 300, "unit": "second"},
                        "targets": [{"minValue": 55}]}]},
            {"type": "step", "length": {"value": 1, "unit": "repetition"},
             "steps": [{"length": {"value": 300, "unit": "second"},
                        "targets": [{"minValue": 100, "maxValue": 100}]}]},
        ]
        poly = _compute_native_polyline(blocks)
        assert any(p[1] == 0.55 for p in poly)

    def test_ensure_preview_noop_on_non_native(self):
        from tp_mcp.tools.library import _ensure_structure_preview
        assert _ensure_structure_preview(None) is None
        assert _ensure_structure_preview({"steps": []}) == {"steps": []}

    def test_ensure_preview_does_not_mutate_caller(self):
        """The helper returns a copy — the caller's structure dict is untouched."""
        from tp_mcp.tools.library import _ensure_structure_preview
        src = {"primaryIntensityMetric": "percentOfFtp",
               "structure": [{"type": "step", "length": {"value": 1, "unit": "repetition"},
                              "steps": [{"length": {"value": 300, "unit": "second"},
                                         "targets": [{"minValue": 90, "maxValue": 90}]}]}]}
        out = _ensure_structure_preview(src)
        assert "polyline" in out
        assert "polyline" not in src            # caller NOT mutated
        assert out is not src


class TestUpdateLibraryItem:
    @pytest.mark.asyncio
    async def test_sets_workout_type_on_sportless_template(self):
        """A template saved with workoutTypeId=0 gets its sport set, and the
        merged value reaches the PUT payload."""
        existing = {"exerciseLibraryItemId": 20, "itemName": "Tempo", "workoutTypeId": 0}
        get_resp = APIResponse(success=True, data=[existing])
        put_resp = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=get_resp)
            mock_instance.put = AsyncMock(return_value=put_resp)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_library_item(
                library_id="1", item_id="20",
                workout_type_id=2, workout_sub_type_id=6,
            )

        assert result["success"] is True
        payload = mock_instance.put.call_args[1]["json"]
        assert payload["workoutTypeId"] == 2
        assert payload["workoutSubTypeId"] == 6

    @pytest.mark.asyncio
    async def test_workout_type_untouched_when_not_passed(self):
        """Omitting the sport params leaves the existing workoutTypeId alone and
        adds no workoutSubTypeId key."""
        existing = {"exerciseLibraryItemId": 21, "itemName": "Endurance", "workoutTypeId": 2}
        get_resp = APIResponse(success=True, data=[existing])
        put_resp = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=get_resp)
            mock_instance.put = AsyncMock(return_value=put_resp)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_library_item(
                library_id="1", item_id="21", name="Endurance v2",
            )

        assert result["success"] is True
        payload = mock_instance.put.call_args[1]["json"]
        assert payload["workoutTypeId"] == 2          # unchanged
        assert "workoutSubTypeId" not in payload
        assert payload["itemName"] == "Endurance v2"  # the field we did change


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
    async def test_single_athlete_ignores_bulk_shape(self):
        """Omitting athletes keeps the original single-athlete result shape."""
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
        assert "scheduled" not in result
        assert "errors" not in result

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


class TestScheduleLibraryWorkoutBulk:
    TEMPLATE = TestScheduleLibraryWorkout.TEMPLATE

    def _mock(self, mock_client, athlete_ids, post_responses):
        items_response = APIResponse(success=True, data=[self.TEMPLATE])
        mock_instance = AsyncMock()
        mock_instance.ensure_athlete_id = AsyncMock(side_effect=athlete_ids)
        mock_instance.get = AsyncMock(return_value=items_response)
        mock_instance.post = AsyncMock(side_effect=post_responses)
        mock_client.return_value.__aenter__.return_value = mock_instance
        return mock_instance

    @pytest.mark.asyncio
    async def test_bulk_schedules_each_athlete(self):
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = self._mock(
                mock_client,
                athlete_ids=[111, 222],
                post_responses=[
                    APIResponse(success=True, data={"workoutId": 1001}),
                    APIResponse(success=True, data={"workoutId": 1002}),
                ],
            )

            result = await tp_schedule_library_workout(
                "1", "10", "2026-04-01", athletes=["Alice", "222"],
            )

        assert result.get("isError") is not True
        assert [s["athlete_id"] for s in result["scheduled"]] == [111, 222]
        assert [s["workout_id"] for s in result["scheduled"]] == [1001, 1002]
        assert result["errors"] == []
        endpoints = [c[0][0] for c in mock_instance.post.call_args_list]
        assert endpoints == [
            "/fitness/v6/athletes/111/workouts",
            "/fitness/v6/athletes/222/workouts",
        ]
        # Each payload targets its own athlete
        payloads = [c[1]["json"] for c in mock_instance.post.call_args_list]
        assert [p["athleteId"] for p in payloads] == [111, 222]
        assert all(p["title"] == "Sweet Spot" for p in payloads)

    @pytest.mark.asyncio
    async def test_bulk_partial_failure_is_not_error(self):
        """One athlete failing is reported in errors, without isError."""
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            self._mock(
                mock_client,
                athlete_ids=[111, 222],
                post_responses=[
                    APIResponse(success=True, data={"workoutId": 1001}),
                    APIResponse(success=False, message="boom"),
                ],
            )

            result = await tp_schedule_library_workout(
                "1", "10", "2026-04-01", athletes=["Alice", "Bob"],
            )

        assert result.get("isError") is not True
        assert len(result["scheduled"]) == 1
        assert result["errors"] == [
            {"athlete": "Bob", "athlete_id": 222, "message": "boom"},
        ]

    @pytest.mark.asyncio
    async def test_bulk_unresolvable_athlete_reported(self):
        """An athlete not in the roster (ensure_athlete_id -> None) is a
        per-athlete error; the rest still get scheduled."""
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = self._mock(
                mock_client,
                athlete_ids=[None, 222],
                post_responses=[
                    APIResponse(success=True, data={"workoutId": 1002}),
                ],
            )

            result = await tp_schedule_library_workout(
                "1", "10", "2026-04-01", athletes=["Nobody", "222"],
            )

        assert result.get("isError") is not True
        assert [s["athlete_id"] for s in result["scheduled"]] == [222]
        assert result["errors"][0]["athlete"] == "Nobody"
        assert mock_instance.post.call_count == 1

    @pytest.mark.asyncio
    async def test_bulk_ambiguous_name_reported(self):
        """ensure_athlete_id raising ValueError (ambiguous name) becomes a
        per-athlete error rather than blowing up the whole call."""
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            self._mock(
                mock_client,
                athlete_ids=[ValueError("Ambiguous athlete name 'Alex'"), 222],
                post_responses=[
                    APIResponse(success=True, data={"workoutId": 1002}),
                ],
            )

            result = await tp_schedule_library_workout(
                "1", "10", "2026-04-01", athletes=["Alex", "222"],
            )

        assert result.get("isError") is not True
        assert "Ambiguous" in result["errors"][0]["message"]
        assert [s["athlete_id"] for s in result["scheduled"]] == [222]

    @pytest.mark.asyncio
    async def test_bulk_total_failure_sets_is_error(self):
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            self._mock(
                mock_client,
                athlete_ids=[111, 222],
                post_responses=[
                    APIResponse(success=False, message="boom"),
                    APIResponse(success=False, message="boom"),
                ],
            )

            result = await tp_schedule_library_workout(
                "1", "10", "2026-04-01", athletes=["Alice", "Bob"],
            )

        assert result["isError"] is True
        assert result["error_code"] == "API_ERROR"
        assert result["scheduled"] == []
        assert len(result["errors"]) == 2

    @pytest.mark.asyncio
    async def test_both_athlete_and_athletes_rejected(self):
        """Passing the single 'athlete' target alongside 'athletes' is a
        validation error before any API call."""
        token = athlete_override.set("Alice")
        try:
            with patch("tp_mcp.tools.library.TPClient") as mock_client:
                result = await tp_schedule_library_workout(
                    "1", "10", "2026-04-01", athletes=["Bob"],
                )
        finally:
            athlete_override.reset(token)

        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"
        assert "not both" in result["message"]
        mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_athletes_list_rejected(self):
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            result = await tp_schedule_library_workout(
                "1", "10", "2026-04-01", athletes=[],
            )

        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"
        mock_client.assert_not_called()
