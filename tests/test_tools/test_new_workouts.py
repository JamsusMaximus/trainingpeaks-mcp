"""Tests for new workout tools: create with structure, update, delete, copy, comments."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools.workouts import (
    tp_add_workout_comment,
    tp_copy_workout,
    tp_create_workout,
    tp_delete_workout,
    tp_get_workout_comments,
    tp_update_workout,
)


class TestCreateWorkoutWithStructure:
    """Tests for tp_create_workout with structure support."""

    @pytest.mark.asyncio
    async def test_create_with_structure_auto_computes_duration(self):
        """Structure should auto-compute duration and TSS."""
        structure = {
            "primaryIntensityMetric": "percentOfFtp",
            "steps": [
                {
                    "name": "WU",
                    "duration_seconds": 600,
                    "intensity_min": 40,
                    "intensity_max": 55,
                    "intensityClass": "warmUp",
                },
                {
                    "name": "Main",
                    "duration_seconds": 1200,
                    "intensity_min": 85,
                    "intensity_max": 95,
                    "intensityClass": "active",
                },
                {
                    "name": "CD",
                    "duration_seconds": 600,
                    "intensity_min": 40,
                    "intensity_max": 55,
                    "intensityClass": "coolDown",
                },
            ],
        }
        create_response = APIResponse(
            success=True,
            data={"workoutId": 7001, "title": "Structured", "workoutDay": "2026-03-01T00:00:00"},
        )

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=create_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_workout(
                date_str="2026-03-01", sport="Bike", title="Structured",
                structure=structure,
            )

        assert result["success"] is True
        payload = mock_instance.post.call_args[1]["json"]
        # Duration auto-computed from structure: 2400s = 40min = 0.667 hours
        assert "totalTimePlanned" in payload
        assert abs(payload["totalTimePlanned"] - 40.0 / 60.0) < 0.01
        # TSS and IF auto-computed with correct semantic mapping (issue #41)
        assert payload["tssPlanned"] == pytest.approx(39.6, abs=0.1)
        assert payload["ifPlanned"] == pytest.approx(0.771, abs=0.001)
        # Guard against IF/TSS swap: IF must be < 1, TSS must be >> 1
        assert payload["ifPlanned"] < 1
        assert payload["tssPlanned"] > 1
        # Structure serialised to JSON string
        assert isinstance(payload["structure"], str)
        parsed = json.loads(payload["structure"])
        assert "structure" in parsed
        assert "polyline" in parsed

    @pytest.mark.asyncio
    async def test_create_with_explicit_duration_overrides_structure(self):
        """Explicit duration should override structure-computed duration."""
        structure = {
            "steps": [
                {
                    "name": "WU",
                    "duration_seconds": 600,
                    "intensity_min": 50,
                    "intensity_max": 60,
                    "intensityClass": "warmUp",
                },
            ],
        }
        create_response = APIResponse(
            success=True,
            data={"workoutId": 7002, "title": "Override", "workoutDay": "2026-03-01T00:00:00"},
        )

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=create_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_workout(
                date_str="2026-03-01", sport="Bike", title="Override",
                duration_minutes=90,  # Override the 10min structure
                structure=structure,
            )

        assert result["success"] is True
        payload = mock_instance.post.call_args[1]["json"]
        assert payload["totalTimePlanned"] == 90 / 60.0  # 1.5 hours

    @pytest.mark.asyncio
    async def test_create_with_tags(self):
        """Tags should be passed in payload."""
        create_response = APIResponse(
            success=True, data={"workoutId": 7003, "title": "Tagged", "workoutDay": "2026-03-01T00:00:00"},
        )

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=create_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_workout(
                date_str="2026-03-01", sport="Run", title="Tagged",
                duration_minutes=60, tags="intervals,hard",
            )

        assert result["success"] is True
        payload = mock_instance.post.call_args[1]["json"]
        assert payload["tags"] == "intervals,hard"

    @pytest.mark.asyncio
    async def test_create_with_feeling_and_rpe(self):
        """Feeling and RPE should be validated and passed."""
        create_response = APIResponse(
            success=True, data={"workoutId": 7004, "title": "Rated", "workoutDay": "2026-03-01T00:00:00"},
        )

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=create_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_workout(
                date_str="2026-03-01", sport="Run", title="Rated",
                duration_minutes=45, feeling=7, rpe=6,
            )

        assert result["success"] is True
        payload = mock_instance.post.call_args[1]["json"]
        assert payload["feeling"] == 7
        assert payload["rpe"] == 6

    @pytest.mark.asyncio
    async def test_create_feeling_out_of_bounds(self):
        """Feeling > 10 should be rejected."""
        result = await tp_create_workout(
            date_str="2026-03-01", sport="Run", title="Bad",
            duration_minutes=30, feeling=11,
        )
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_create_rpe_out_of_bounds(self):
        """RPE < 1 should be rejected."""
        result = await tp_create_workout(
            date_str="2026-03-01", sport="Run", title="Bad",
            duration_minutes=30, rpe=0,
        )
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_create_without_duration_or_structure(self):
        """Should fail if no duration, simplified structure, or raw structure provided."""
        result = await tp_create_workout(
            date_str="2026-03-01", sport="Run", title="No Duration",
        )
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_create_with_structured_workout_serialises(self):
        """Raw structured_workout should be serialized unchanged for POST."""
        structured_workout = {
            "structure": [],
            "polyline": [],
            "primaryLengthMetric": "duration",
            "primaryIntensityMetric": "percentOfFtp",
            "primaryIntensityTargetOrRange": "range",
        }
        create_response = APIResponse(
            success=True,
            data={"workoutId": 7005, "title": "Structured Raw", "workoutDay": "2026-03-01T00:00:00"},
        )

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=create_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_workout(
                date_str="2026-03-01",
                sport="Bike",
                title="Structured Raw",
                structured_workout=structured_workout,
            )

        assert result["success"] is True
        payload = mock_instance.post.call_args[1]["json"]
        assert json.loads(payload["structure"]) == structured_workout

    @pytest.mark.asyncio
    async def test_create_rejects_both_structure_inputs(self):
        """Simplified structure and raw structured_workout cannot be combined."""
        result = await tp_create_workout(
            date_str="2026-03-01",
            sport="Bike",
            title="Conflict",
            structure={"steps": [{"name": "WU", "duration_seconds": 60, "intensity_min": 50, "intensity_max": 60}]},
            structured_workout={"structure": []},
        )
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"
        assert "Provide only one of structure or structured_workout" in result["message"]

    @pytest.mark.asyncio
    async def test_create_rejects_invalid_structured_workout(self):
        """Raw structured_workout should be validated before POST."""
        result = await tp_create_workout(
            date_str="2026-03-01",
            sport="Bike",
            title="Bad Structured Raw",
            structured_workout={"structure": []},
        )
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"
        assert "structured_workout" in result["message"]


class TestUpdateWorkout:
    """Tests for tp_update_workout."""

    @pytest.mark.asyncio
    async def test_update_merges_with_existing(self):
        """Update should GET existing, merge updates, then PUT."""
        existing = {
            "workoutId": 1001,
            "title": "Original",
            "workoutDay": "2026-03-01T00:00:00",
            "workoutTypeFamilyId": 3,
            "workoutTypeValueId": 3,
        }
        get_response = APIResponse(success=True, data=existing)
        put_response = APIResponse(success=True, data=None)

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=get_response)
            mock_instance.put = AsyncMock(return_value=put_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_workout(workout_id="1001", title="Updated Title")

        assert result["success"] is True
        put_payload = mock_instance.put.call_args[1]["json"]
        assert put_payload["title"] == "Updated Title"
        # Original fields preserved
        assert put_payload["workoutTypeFamilyId"] == 3

    @pytest.mark.asyncio
    async def test_update_sport_changes_ids(self):
        """Changing sport should update family and type IDs."""
        existing = {
            "workoutId": 1001,
            "workoutTypeFamilyId": 3,
            "workoutTypeValueId": 3,
        }
        get_response = APIResponse(success=True, data=existing)
        put_response = APIResponse(success=True, data=None)

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=get_response)
            mock_instance.put = AsyncMock(return_value=put_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_workout(workout_id="1001", sport="Bike")

        assert result["success"] is True
        put_payload = mock_instance.put.call_args[1]["json"]
        assert put_payload["workoutTypeFamilyId"] == 2
        assert put_payload["workoutTypeValueId"] == 2

    @pytest.mark.asyncio
    async def test_update_date_only_sets_midnight(self):
        """Date-only updates should keep the existing midnight behavior."""
        existing = {"workoutId": 1001, "workoutDay": "2026-03-01T00:00:00"}
        get_response = APIResponse(success=True, data=existing)
        put_response = APIResponse(success=True, data=None)

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=get_response)
            mock_instance.put = AsyncMock(return_value=put_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_workout(workout_id="1001", date="2026-04-14")

        assert result["success"] is True
        put_payload = mock_instance.put.call_args[1]["json"]
        assert put_payload["workoutDay"] == "2026-04-14T00:00:00"

    @pytest.mark.asyncio
    async def test_update_date_only_preserves_existing_planned_start_time(self):
        """Date-only updates should move an existing planned start to the new day."""
        existing = {
            "workoutId": 1001,
            "workoutDay": "2026-03-01T00:00:00",
            "startTimePlanned": "2026-03-01T16:45:00",
        }
        get_response = APIResponse(success=True, data=existing)
        put_response = APIResponse(success=True, data=None)

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=get_response)
            mock_instance.put = AsyncMock(return_value=put_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_workout(workout_id="1001", date="2026-04-14")

        assert result["success"] is True
        put_payload = mock_instance.put.call_args[1]["json"]
        assert put_payload["workoutDay"] == "2026-04-14T00:00:00"
        assert put_payload["startTimePlanned"] == "2026-04-14T16:45:00"

    @pytest.mark.asyncio
    async def test_update_datetime_preserves_time(self):
        """Datetime updates should forward the scheduled time to TrainingPeaks."""
        existing = {
            "workoutId": 1001,
            "workoutDay": "2026-03-01T00:00:00",
            "startTimePlanned": "2026-03-01T09:30:00",
        }
        get_response = APIResponse(success=True, data=existing)
        put_response = APIResponse(success=True, data=None)

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=get_response)
            mock_instance.put = AsyncMock(return_value=put_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_workout(workout_id="1001", date="2026-04-14T16:45:00")

        assert result["success"] is True
        put_payload = mock_instance.put.call_args[1]["json"]
        assert put_payload["workoutDay"] == "2026-04-14T00:00:00"
        assert put_payload["startTimePlanned"] == "2026-04-14T16:45:00"

    @pytest.mark.asyncio
    async def test_update_with_structure_serialises(self):
        """Simplified structure should be converted to TP wire format for PUT."""
        existing = {"workoutId": 1001}
        get_response = APIResponse(success=True, data=existing)
        put_response = APIResponse(success=True, data=None)
        structure = {
            "primaryIntensityMetric": "percentOfFtp",
            "steps": [
                {
                    "name": "WU",
                    "duration_seconds": 600,
                    "intensity_min": 40,
                    "intensity_max": 55,
                    "intensityClass": "warmUp",
                },
                {
                    "name": "Main",
                    "duration_seconds": 1200,
                    "intensity_min": 85,
                    "intensity_max": 95,
                    "intensityClass": "active",
                },
                {
                    "name": "CD",
                    "duration_seconds": 600,
                    "intensity_min": 40,
                    "intensity_max": 55,
                    "intensityClass": "coolDown",
                },
            ],
        }

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=get_response)
            mock_instance.put = AsyncMock(return_value=put_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_workout(
                workout_id="1001",
                structure=structure,
            )

        assert result["success"] is True
        put_payload = mock_instance.put.call_args[1]["json"]
        assert isinstance(put_payload["structure"], str)
        parsed = json.loads(put_payload["structure"])
        assert "structure" in parsed
        assert "polyline" in parsed
        assert abs(put_payload["totalTimePlanned"] - 40.0 / 60.0) < 0.01
        # Exact IF/TSS values with swap guard (issue #41)
        assert put_payload["tssPlanned"] == pytest.approx(39.6, abs=0.1)
        assert put_payload["ifPlanned"] == pytest.approx(0.771, abs=0.001)
        assert put_payload["ifPlanned"] < 1
        assert put_payload["tssPlanned"] > 1

    @pytest.mark.asyncio
    async def test_update_with_structure_explicit_duration_and_tss_override(self):
        """Explicit duration and TSS should win over derived structure values."""
        existing = {
            "workoutId": 1001,
            "ifPlanned": 0.91,
        }
        get_response = APIResponse(success=True, data=existing)
        put_response = APIResponse(success=True, data=None)
        structure = {
            "steps": [
                {
                    "name": "WU",
                    "duration_seconds": 600,
                    "intensity_min": 50,
                    "intensity_max": 60,
                    "intensityClass": "warmUp",
                },
            ],
        }

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=get_response)
            mock_instance.put = AsyncMock(return_value=put_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_workout(
                workout_id="1001",
                duration_minutes=90,
                tss_planned=77,
                structure=structure,
            )

        assert result["success"] is True
        put_payload = mock_instance.put.call_args[1]["json"]
        assert put_payload["totalTimePlanned"] == 90 / 60.0
        assert put_payload["tssPlanned"] == 77
        assert "ifPlanned" not in put_payload

    @pytest.mark.asyncio
    async def test_update_with_invalid_structure_returns_validation_error(self):
        """Invalid simplified structure should fail before PUT."""
        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock()
            mock_instance.put = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_workout(
                workout_id="1001",
                structure={"structure": [{"type": "step"}]},
            )

        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"
        mock_instance.get.assert_not_called()
        mock_instance.put.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_with_structured_workout_serialises(self):
        """Raw structured_workout should be serialized unchanged for PUT."""
        existing = {"workoutId": 1001}
        get_response = APIResponse(success=True, data=existing)
        put_response = APIResponse(success=True, data=None)
        structured_workout = {
            "structure": [],
            "polyline": [],
            "primaryLengthMetric": "duration",
            "primaryIntensityMetric": "percentOfFtp",
            "primaryIntensityTargetOrRange": "range",
        }

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=get_response)
            mock_instance.put = AsyncMock(return_value=put_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_workout(
                workout_id="1001",
                structured_workout=structured_workout,
            )

        assert result["success"] is True
        put_payload = mock_instance.put.call_args[1]["json"]
        assert json.loads(put_payload["structure"]) == structured_workout

    @pytest.mark.asyncio
    async def test_update_rejects_both_structure_inputs(self):
        """Simplified structure and raw structured_workout cannot be combined."""
        result = await tp_update_workout(
            workout_id="1001",
            structure={"steps": [{"name": "WU", "duration_seconds": 60, "intensity_min": 50, "intensity_max": 60}]},
            structured_workout={"structure": []},
        )
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"
        assert "Provide only one of structure or structured_workout" in result["message"]

    @pytest.mark.asyncio
    async def test_update_rejects_invalid_structured_workout(self):
        """Raw structured_workout should be validated before PUT."""
        result = await tp_update_workout(
            workout_id="1001",
            structured_workout={"structure": []},
        )
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"
        assert "structured_workout" in result["message"]


class TestDeleteWorkout:
    """Tests for tp_delete_workout."""

    @pytest.mark.asyncio
    async def test_delete_success(self):
        delete_response = APIResponse(success=True, data=None)

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.delete = AsyncMock(return_value=delete_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_delete_workout("1001")

        assert result["success"] is True
        mock_instance.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_invalid_id(self):
        result = await tp_delete_workout("abc")
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"


class TestCopyWorkout:
    """Tests for tp_copy_workout."""

    @pytest.mark.asyncio
    async def test_copy_preserves_structure(self):
        """Copy should preserve structure, description, sport type."""
        source = {
            "workoutId": 1001,
            "title": "Source Workout",
            "workoutTypeFamilyId": 2,
            "workoutTypeValueId": 2,
            "totalTimePlanned": 1.5,
            "tssPlanned": 80,
            "description": "Test desc",
            "coachComments": "Coach says...",
            "structure": '{"structure": []}',
        }
        get_response = APIResponse(success=True, data=source)
        post_response = APIResponse(success=True, data={"workoutId": 2001, "title": "Source Workout"})

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=get_response)
            mock_instance.post = AsyncMock(return_value=post_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_copy_workout("1001", "2026-04-01")

        assert result["success"] is True
        assert result["copied_from"] == 1001
        payload = mock_instance.post.call_args[1]["json"]
        assert payload["workoutDay"] == "2026-04-01T00:00:00"
        assert payload["workoutTypeFamilyId"] == 2
        assert payload["totalTimePlanned"] == 1.5
        assert payload["tssPlanned"] == 80
        assert payload["description"] == "Test desc"
        assert payload["coachComments"] == "Coach says..."
        assert "structure" in payload

    @pytest.mark.asyncio
    async def test_copy_does_not_copy_actual_data(self):
        """Copy should not include actual/completed data."""
        source = {
            "workoutId": 1001,
            "title": "Done",
            "workoutTypeFamilyId": 3,
            "workoutTypeValueId": 3,
            "totalTimePlanned": 1.0,
            "totalTime": 0.95,
            "tssActual": 75,
            "completed": True,
        }
        get_response = APIResponse(success=True, data=source)
        post_response = APIResponse(success=True, data={"workoutId": 2002})

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=get_response)
            mock_instance.post = AsyncMock(return_value=post_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_copy_workout("1001", "2026-04-01")

        assert result["success"] is True
        payload = mock_instance.post.call_args[1]["json"]
        assert "totalTime" not in payload
        assert "tssActual" not in payload
        assert "completed" not in payload

    @pytest.mark.asyncio
    async def test_copy_with_title_override(self):
        source = {"workoutId": 1001, "title": "Old", "workoutTypeFamilyId": 3, "workoutTypeValueId": 3}
        get_response = APIResponse(success=True, data=source)
        post_response = APIResponse(success=True, data={"workoutId": 2003, "title": "New Title"})

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=get_response)
            mock_instance.post = AsyncMock(return_value=post_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            await tp_copy_workout("1001", "2026-04-01", title="New Title")

        payload = mock_instance.post.call_args[1]["json"]
        assert payload["title"] == "New Title"


class TestWorkoutComments:
    """Tests for workout comment tools."""

    @pytest.mark.asyncio
    async def test_get_comments_success(self):
        comments_data = [
            {"id": 1, "value": "Great workout!", "createdAt": "2026-03-01"},
            {"id": 2, "value": "Thanks coach", "createdAt": "2026-03-02"},
        ]
        response = APIResponse(success=True, data=comments_data)

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_workout_comments("1001")

        assert result["count"] == 2
        assert len(result["comments"]) == 2

    @pytest.mark.asyncio
    async def test_get_comments_empty(self):
        response = APIResponse(success=True, data=[])

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_workout_comments("1001")

        assert result["count"] == 0
        assert "No comments" in result.get("message", "")

    @pytest.mark.asyncio
    async def test_add_comment_success(self):
        response = APIResponse(success=True, data=None)

        with patch("tp_mcp.tools.workouts.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_add_workout_comment("1001", "Nice ride!")

        assert result["success"] is True
        payload = mock_instance.post.call_args[1]["json"]
        assert payload["value"] == "Nice ride!"

    @pytest.mark.asyncio
    async def test_add_empty_comment_rejected(self):
        result = await tp_add_workout_comment("1001", "")
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"
