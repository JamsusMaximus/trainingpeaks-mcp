"""Tests for workout library tools."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools.library import (
    tp_create_library,
    tp_create_library_item,
    tp_create_strength_workout,
    tp_delete_library,
    tp_get_libraries,
    tp_get_library_items,
    tp_schedule_library_workout,
)


class TestGetLibraries:
    @pytest.mark.asyncio
    async def test_list_libraries(self):
        data = [
            {"exerciseLibraryId": 1, "libraryName": "My Workouts", "isDefault": False, "itemCount": 5},
            {"exerciseLibraryId": 2, "libraryName": "Default", "isDefault": True, "itemCount": 20},
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
        response = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_schedule_library_workout("1", "10", "2026-04-01")

        assert result["success"] is True

        call_args = mock_instance.post.call_args
        endpoint = call_args[0][0]
        payload = call_args[1]["json"]
        base_url = call_args[1]["base_url"]

        assert endpoint == "/rx/activity/v1/libraryContent/workoutLibrary/applyToCalendar"
        assert base_url == "https://api.peakswaresb.com"
        assert payload == {
            "calendarId": 123,
            "workoutLibraryItemId": 10,
            "prescribedDate": "2026-04-01",
            "prescribedStartTime": None,
            "orderOnDay": 1,
        }


class TestCreateStrengthWorkout:
    @pytest.mark.asyncio
    async def test_invalid_date(self):
        result = await tp_create_strength_workout(
            date="not-a-date", title="Strength", blocks=[{"blockType": "SingleExercise", "title": "X", "exercises": []}],
        )
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_empty_title(self):
        result = await tp_create_strength_workout(
            date="2026-04-01", title="   ", blocks=[{"blockType": "SingleExercise", "title": "X", "exercises": []}],
        )
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_empty_blocks(self):
        result = await tp_create_strength_workout(
            date="2026-04-01", title="Strength", blocks=[],
        )
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_creates_with_correct_payload(self):
        response = APIResponse(success=True, data={"id": 999})
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            blocks = [
                {
                    "blockType": "WarmUp",
                    "title": "Warm-up",
                    "coachNotes": "Easy",
                    "exercises": [
                        {
                            "exercise_id": "100",
                            "exercise_title": "Air Squat",
                            "sets": [
                                {"parameter": "Reps", "value": 10},
                                {"parameter": "Reps", "value": 10},
                            ],
                        },
                    ],
                },
                {
                    "blockType": "SingleExercise",
                    "title": "Back Squat",
                    "exercises": [
                        {
                            "exercise_id": "200",
                            "exercise_title": "Back Squat",
                            "sets": [
                                {"parameter": "Reps", "value": 5},
                                {"parameter": "Reps", "value": 5},
                                {"parameter": "Reps", "value": 5},
                            ],
                        },
                    ],
                },
            ]

            result = await tp_create_strength_workout(
                date="2026-04-01", title="Strength A", blocks=blocks,
            )

        assert result["success"] is True
        assert result["title"] == "Strength A"
        assert result["date"] == "2026-04-01"
        assert result["block_count"] == 2
        assert result["workout_id"] == 999

        call_args = mock_instance.post.call_args
        endpoint = call_args[0][0]
        payload = call_args[1]["json"]
        base_url = call_args[1]["base_url"]

        assert endpoint == "/rx/activity/v1/workouts/save"
        assert base_url == "https://api.peakswaresb.com"

        assert payload["workoutType"] == "StructuredStrength"
        assert payload["calendarId"] == 123
        assert payload["title"] == "Strength A"
        assert payload["prescribedDate"] == "2026-04-01"
        assert payload["orderOnDay"] == 1
        assert payload["isHidden"] is False
        assert payload["isLocked"] is False
        assert payload["complianceState"] == "Unplanned"

        assert len(payload["blocks"]) == 2
        warmup = payload["blocks"][0]
        assert warmup["blockType"] == "WarmUp"
        assert warmup["title"] == "Warm-up"
        assert warmup["coachNotes"] == "Easy"
        assert warmup["parameters"] == []
        assert warmup["isComplete"] is False
        assert warmup["compliancePercent"] == 0
        assert warmup["complianceState"] == "NoCompletion"
        # UUIDs are string-typed
        assert isinstance(warmup["id"], str) and len(warmup["id"]) == 36

        prescription = warmup["prescriptions"][0]
        ex = prescription["exercise"]
        assert ex["id"] == "100"
        assert ex["title"] == "Air Squat"
        assert ex["ownerId"] == 2000301
        assert ex["videoUrl"] == ""
        assert ex["instructions"] == ""
        assert ex["primaryMuscleGroups"] == []
        assert ex["secondaryMuscleGroups"] == []
        assert ex["canEdit"] is False
        # Exercise parameters must mirror the prescription-level parameters array
        assert ex["parameters"] == prescription["parameters"]
        assert prescription["coachNotes"] is None
        assert prescription["complianceState"] == "NoCompletion"
        assert prescription["setSummaryTemplate"] == "{Reps} Reps"

        # Single shared parameter column
        assert len(prescription["parameters"]) == 1
        param = prescription["parameters"][0]
        assert param["parameter"] == "Reps"
        assert param["title"] == "Reps"
        assert param["category"] == "Reps"
        assert param["unit"] == {"title": "Reps", "abbreviation": "", "unit": "Reps"}

        # Two sets, each with one parameterValue
        assert len(prescription["sets"]) == 2
        for s in prescription["sets"]:
            assert s["isComplete"] is False
            assert s["setOrigin"] == "Prescribed"
            assert len(s["parameterValues"]) == 1
            pv = s["parameterValues"][0]
            assert pv["parameter"] == "Reps"
            assert pv["inputFormat"] == "Integer"
            assert pv["prescribedValue"] == "10"
            assert pv["executedValue"] is None

        # Back Squat: 3 sets of 5 reps
        squat = payload["blocks"][1]
        assert squat["blockType"] == "SingleExercise"
        assert squat["coachNotes"] is None
        assert len(squat["prescriptions"][0]["sets"]) == 3
        assert all(
            s["parameterValues"][0]["prescribedValue"] == "5"
            for s in squat["prescriptions"][0]["sets"]
        )

    @pytest.mark.asyncio
    async def test_unique_uuids_per_field(self):
        response = APIResponse(success=True, data={})
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            blocks = [
                {
                    "blockType": "SingleExercise",
                    "title": "Bench",
                    "exercises": [
                        {
                            "exercise_id": "300",
                            "exercise_title": "Bench Press",
                            "sets": [
                                {"parameter": "Reps", "value": 8},
                                {"parameter": "Reps", "value": 8},
                            ],
                        },
                    ],
                },
            ]
            await tp_create_strength_workout(
                date="2026-04-01", title="W", blocks=blocks,
            )

        payload = mock_instance.post.call_args[1]["json"]
        block = payload["blocks"][0]
        prescription = block["prescriptions"][0]

        ids = [
            block["id"],
            prescription["id"],
            prescription["parameters"][0]["id"],
            prescription["sets"][0]["id"],
            prescription["sets"][1]["id"],
            prescription["sets"][0]["parameterValues"][0]["id"],
            prescription["sets"][1]["parameterValues"][0]["id"],
        ]
        # All UUIDs distinct
        assert len(set(ids)) == len(ids)

    @pytest.mark.asyncio
    async def test_auth_failure(self):
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=None)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_strength_workout(
                date="2026-04-01",
                title="Strength",
                blocks=[
                    {
                        "blockType": "SingleExercise",
                        "title": "X",
                        "exercises": [],
                    }
                ],
            )

        assert result["isError"] is True
        assert result["error_code"] == "AUTH_INVALID"

    @pytest.mark.asyncio
    async def test_duration_parameter_serialization(self):
        """Duration parameters use inputFormat='Time', string prescribedValue, and bare template."""
        response = APIResponse(success=True, data={"id": 1})
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            blocks = [
                {
                    "blockType": "SingleExercise",
                    "title": "Plank",
                    "exercises": [
                        {
                            "exercise_id": "400",
                            "exercise_title": "Plank",
                            "sets": [
                                {"parameter": "Duration", "value": 30},
                                {"parameter": "Duration", "value": 45},
                            ],
                        },
                    ],
                },
            ]
            await tp_create_strength_workout(
                date="2026-04-01", title="Core", blocks=blocks,
            )

        payload = mock_instance.post.call_args[1]["json"]
        prescription = payload["blocks"][0]["prescriptions"][0]

        assert prescription["setSummaryTemplate"] == "{Duration}"
        assert prescription["parameters"][0]["parameter"] == "Duration"
        assert prescription["parameters"][0]["category"] == "Duration"
        assert prescription["parameters"][0]["unit"] == {
            "title": "Seconds",
            "abbreviation": "sec",
            "unit": "Seconds",
        }

        pv0 = prescription["sets"][0]["parameterValues"][0]
        pv1 = prescription["sets"][1]["parameterValues"][0]
        assert pv0["inputFormat"] == "Time"
        assert pv0["prescribedValue"] == "30"
        assert pv1["inputFormat"] == "Time"
        assert pv1["prescribedValue"] == "45"

    @pytest.mark.asyncio
    async def test_weightlb_parameter_serialization(self):
        """WeightLb parameters use inputFormat='Decimal', string-or-None prescribedValue."""
        response = APIResponse(success=True, data={"id": 1})
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            blocks = [
                {
                    "blockType": "SingleExercise",
                    "title": "Bench",
                    "exercises": [
                        {
                            "exercise_id": "500",
                            "exercise_title": "Bench Press",
                            "sets": [
                                {"parameter": "WeightLb", "value": 135},
                                {"parameter": "WeightLb", "value": None},
                            ],
                        },
                    ],
                },
            ]
            await tp_create_strength_workout(
                date="2026-04-01", title="Bench Day", blocks=blocks,
            )

        payload = mock_instance.post.call_args[1]["json"]
        prescription = payload["blocks"][0]["prescriptions"][0]

        assert prescription["setSummaryTemplate"] == "{WeightLb} lbs"
        assert prescription["parameters"][0]["unit"] == {
            "title": "Pounds",
            "abbreviation": "lb",
            "unit": "Pounds",
        }
        pv0 = prescription["sets"][0]["parameterValues"][0]
        pv1 = prescription["sets"][1]["parameterValues"][0]
        assert pv0["inputFormat"] == "Decimal"
        assert pv0["prescribedValue"] == "135"
        assert pv1["inputFormat"] == "Decimal"
        assert pv1["prescribedValue"] is None

    @pytest.mark.asyncio
    async def test_exercise_video_url_and_instructions_passthrough(self):
        """Optional video_url and instructions on the exercise are passed through."""
        response = APIResponse(success=True, data={"id": 1})
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            blocks = [
                {
                    "blockType": "SingleExercise",
                    "title": "Custom",
                    "exercises": [
                        {
                            "exercise_id": "600",
                            "exercise_title": "Custom Lift",
                            "video_url": "https://example.com/v.mp4",
                            "instructions": "Lift with form.",
                            "sets": [{"parameter": "Reps", "value": 8}],
                        },
                    ],
                },
            ]
            await tp_create_strength_workout(
                date="2026-04-01", title="Custom Day", blocks=blocks,
            )

        payload = mock_instance.post.call_args[1]["json"]
        ex = payload["blocks"][0]["prescriptions"][0]["exercise"]
        assert ex["videoUrl"] == "https://example.com/v.mp4"
        assert ex["instructions"] == "Lift with form."
