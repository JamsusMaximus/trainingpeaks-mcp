"""Tests for structured strength workout tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools.strength import (
    _build_payload,
    _input_format,
    _validate_blocks,
    tp_create_strength_workout,
    tp_delete_strength_workout,
    tp_get_strength_summary,
    tp_search_exercises,
)

TEST_ATHLETE_ID = 123456
TEST_ACCESS_TOKEN = "test_access_token"


def _mock_tp_client(athlete_id=TEST_ATHLETE_ID):
    mock_client = AsyncMock()
    mock_client.ensure_athlete_id = AsyncMock(return_value=athlete_id)
    mock_client._ensure_access_token = AsyncMock(return_value=APIResponse(success=True))
    cache = MagicMock()
    cache.access_token = TEST_ACCESS_TOKEN
    mock_client._token_cache = cache
    return mock_client


def _mock_http(status_code, json_data):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    http = AsyncMock()
    http.post.return_value = resp
    http.get.return_value = resp
    http.delete.return_value = resp
    return http


# ── Offline exercise search ──────────────────────────────────────────────────


class TestSearchExercises:
    @pytest.mark.asyncio
    async def test_name_match_exact_first(self):
        r = await tp_search_exercises("air squat")
        assert r["count"] >= 1
        assert r["exercises"][0]["title"] == "Air Squat"
        assert r["exercises"][0]["id"] == "1"
        assert r["exercises"][0]["video_url"]

    @pytest.mark.asyncio
    async def test_substring(self):
        r = await tp_search_exercises("squat", limit=5)
        assert r["count"] == 5
        assert all("squat" in e["title"].lower() for e in r["exercises"])

    @pytest.mark.asyncio
    async def test_muscle_group_filter(self):
        r = await tp_search_exercises("", muscle_group="glute", limit=3)
        assert r["count"] >= 1

    @pytest.mark.asyncio
    async def test_empty_query_errors(self):
        r = await tp_search_exercises("")
        assert r.get("error_code") == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_limit_capped(self):
        r = await tp_search_exercises("a", limit=1000)
        assert r["count"] <= 100

    @pytest.mark.asyncio
    async def test_exact_match_past_limit_still_surfaces(self):
        """Regression: ranking must happen BEFORE truncation. With the exact
        match last in catalogue order and limit=1, it must still win — not be
        cut by an earlier substring match."""
        def _ex(eid, title):
            return {"id": eid, "title": title, "videoUrl": None,
                    "primaryMuscleGroups": [], "secondaryMuscleGroups": [],
                    "parameters": []}
        catalogue = {
            "1": _ex("1", "Back Squat"),
            "2": _ex("2", "Front Squat"),
            "3": _ex("3", "Squat"),  # exact, but last
        }
        with patch("tp_mcp.tools.strength._catalogue", return_value=catalogue):
            r = await tp_search_exercises("squat", limit=1)
        assert r["count"] == 1
        assert r["exercises"][0]["title"] == "Squat"


# ── Validation (returns before any network call) ─────────────────────────────


class TestValidation:
    def test_empty_blocks(self):
        assert _validate_blocks([]) is not None

    def test_bad_block_type(self):
        err = _validate_blocks([{"type": "Nope", "exercises": [{"id": "1", "sets": [{"Reps": "8"}]}]}])
        assert err and "type" in err

    def test_unknown_exercise(self):
        err = _validate_blocks([{"type": "SingleExercise", "exercises": [{"id": "999999", "sets": [{"Reps": "8"}]}]}])
        assert err and "not in the exercise library" in err

    def test_unknown_parameter(self):
        err = _validate_blocks([{"type": "SingleExercise", "exercises": [{"id": "1", "sets": [{"Repz": "8"}]}]}])
        assert err and "unknown parameter" in err

    def test_no_sets(self):
        err = _validate_blocks([{"type": "SingleExercise", "exercises": [{"id": "1", "sets": []}]}])
        assert err and "no sets" in err

    def test_superset_unequal_sets(self):
        err = _validate_blocks([{
            "type": "Superset",
            "exercises": [
                {"id": "1", "sets": [{"Reps": "8"}, {"Reps": "8"}]},
                {"id": "6", "sets": [{"Reps": "8"}]},
            ],
        }])
        assert err and "same number of sets" in err

    def test_superset_equal_sets_ok(self):
        err = _validate_blocks([{
            "type": "Superset",
            "exercises": [
                {"id": "1", "sets": [{"Reps": "8"}, {"Reps": "8"}]},
                {"id": "6", "sets": [{"Reps": "12"}, {"Reps": "12"}]},
            ],
        }])
        assert err is None


# ── Payload construction ─────────────────────────────────────────────────────


class TestBuildPayload:
    def test_input_format(self):
        assert _input_format("Reps") == "Integer"
        assert _input_format("RepsPerSide") == "Integer"
        assert _input_format("WeightKg") == "Decimal"
        assert _input_format("Duration") == "Decimal"

    def test_structure_and_counts(self):
        blocks = [
            {"type": "WarmUp", "exercises": [{"id": "1", "sets": [{"Reps": "10"}]}]},
            {"type": "Superset", "exercises": [
                {"id": "50", "sets": [{"Reps": "8", "WeightKg": "24"}, {"Reps": "6", "WeightKg": "28"}]},
                {"id": "6", "sets": [{"Reps": "12"}, {"Reps": "12"}]},
            ]},
        ]
        p = _build_payload(999, "2027-01-06", "Day", blocks, "instr")
        assert p["workoutType"] == "StructuredStrength"
        assert p["calendarId"] == 999
        assert p["prescribedDate"] == "2027-01-06"
        assert p["snapshot"] == {"totalBlocks": 2, "completedBlocks": 0, "totalSets": 5, "completedSets": 0}
        assert [b["blockType"] for b in p["blocks"]] == ["WarmUp", "Superset"]
        # exercise.parameters is sent empty (server enriches from its library)
        assert p["blocks"][0]["prescriptions"][0]["exercise"]["parameters"] == []

    def test_prescription_columns_and_format(self):
        blocks = [{"type": "SingleExercise", "exercises": [
            {"id": "50", "sets": [{"Reps": "8", "WeightKg": "24"}]}]}]
        presc = _build_payload(1, "2027-01-06", "x", blocks, None)["blocks"][0]["prescriptions"][0]
        cols = {c["parameter"]: c["inputFormat"] for c in presc["parameters"]}
        assert cols == {"Reps": "Integer", "WeightKg": "Decimal"}
        pv = presc["sets"][0]["parameterValues"]
        assert {v["parameter"]: v["prescribedValue"] for v in pv} == {"Reps": "8", "WeightKg": "24"}
        assert all(v["executedValue"] is None for v in pv)


# ── API-calling tools (mocked) ───────────────────────────────────────────────


class TestCreate:
    @pytest.mark.asyncio
    async def test_success(self):
        blocks = [{"type": "SingleExercise", "exercises": [{"id": "1", "sets": [{"Reps": "10"}]}]}]
        http = _mock_http(200, {"data": {"id": "555", "snapshot": {"totalBlocks": 1, "totalSets": 1}}})
        with patch("tp_mcp.tools.strength.TPClient") as mtp:
            mtp.return_value.__aenter__.return_value = _mock_tp_client()
            with patch("tp_mcp.tools.strength.httpx.AsyncClient") as mh:
                mh.return_value.__aenter__.return_value = http
                r = await tp_create_strength_workout(date="2027-01-06", title="Day", blocks=blocks)
        assert r["workout_id"] == "555"
        assert r["total_sets"] == 1

    @pytest.mark.asyncio
    async def test_validation_blocks_before_network(self):
        # Unknown exercise → VALIDATION_ERROR, no client touched.
        blocks = [{"type": "SingleExercise", "exercises": [{"id": "0", "sets": [{"Reps": "8"}]}]}]
        r = await tp_create_strength_workout(date="2027-01-06", title="x", blocks=blocks)
        assert r["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_api_error_surfaces_server_validation(self):
        blocks = [{"type": "SingleExercise", "exercises": [{"id": "1", "sets": [{"Reps": "10"}]}]}]
        http = _mock_http(400, {"errors": {"blocks[0]": ["bad"]}})
        with patch("tp_mcp.tools.strength.TPClient") as mtp:
            mtp.return_value.__aenter__.return_value = _mock_tp_client()
            with patch("tp_mcp.tools.strength.httpx.AsyncClient") as mh:
                mh.return_value.__aenter__.return_value = http
                r = await tp_create_strength_workout(date="2027-01-06", title="Day", blocks=blocks)
        assert r["error_code"] == "API_ERROR"
        assert "bad" in r["message"]

    @pytest.mark.asyncio
    async def test_auth_failure(self):
        blocks = [{"type": "SingleExercise", "exercises": [{"id": "1", "sets": [{"Reps": "10"}]}]}]
        with patch("tp_mcp.tools.strength.TPClient") as mtp:
            mtp.return_value.__aenter__.return_value = _mock_tp_client(athlete_id=None)
            r = await tp_create_strength_workout(date="2027-01-06", title="Day", blocks=blocks)
        assert r["error_code"] == "AUTH_INVALID"


class TestSummaryAndDelete:
    @pytest.mark.asyncio
    async def test_summary(self):
        http = _mock_http(200, {"data": {"complianceState": "NoCompletion", "totalSets": 6, "completedSets": 2}})
        with patch("tp_mcp.tools.strength.TPClient") as mtp:
            mtp.return_value.__aenter__.return_value = _mock_tp_client()
            with patch("tp_mcp.tools.strength.httpx.AsyncClient") as mh:
                mh.return_value.__aenter__.return_value = http
                r = await tp_get_strength_summary(workout_id="555")
        assert r["compliance_state"] == "NoCompletion"
        assert r["total_sets"] == 6 and r["completed_sets"] == 2

    @pytest.mark.asyncio
    async def test_delete(self):
        http = _mock_http(200, {"data": 555, "errors": {}})
        with patch("tp_mcp.tools.strength.TPClient") as mtp:
            mtp.return_value.__aenter__.return_value = _mock_tp_client()
            with patch("tp_mcp.tools.strength.httpx.AsyncClient") as mh:
                mh.return_value.__aenter__.return_value = http
                r = await tp_delete_strength_workout(workout_id="555")
        assert r["deleted"] is True

    @pytest.mark.asyncio
    async def test_summary_not_found(self):
        http = _mock_http(404, {"message": "nope"})
        with patch("tp_mcp.tools.strength.TPClient") as mtp:
            mtp.return_value.__aenter__.return_value = _mock_tp_client()
            with patch("tp_mcp.tools.strength.httpx.AsyncClient") as mh:
                mh.return_value.__aenter__.return_value = http
                r = await tp_get_strength_summary(workout_id="555")
        assert r["error_code"] == "NOT_FOUND"
