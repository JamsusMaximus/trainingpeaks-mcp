"""Tests for structured strength workout tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools.strength import (
    _build_payload,
    _fmt_set,
    _fmt_workout_detail,
    _input_format,
    _min,
    _validate_blocks,
    tp_create_strength_workout,
    tp_delete_strength_workout,
    tp_get_strength_summary,
    tp_get_strength_workout,
    tp_get_strength_workouts,
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


# ── Detail projection helpers (pure) ─────────────────────────────────────────


class TestDetailHelpers:
    def test_min_conversion(self):
        assert _min(2400) == 40.0
        assert _min(2612) == 43.5
        assert _min(None) is None
        assert _min("bad") is None

    def test_fmt_set_splits_prescribed_executed(self):
        s = {
            "isComplete": True,
            "parameterValues": [
                {"parameter": "Reps", "prescribedValue": "10", "executedValue": "8"},
                {"parameter": "WeightKg", "prescribedValue": "24", "executedValue": None},
            ],
        }
        out = _fmt_set(s)
        assert out["prescribed"] == {"Reps": "10", "WeightKg": "24"}
        assert out["executed"] == {"Reps": "8"}  # None executed value dropped
        assert out["complete"] is True

    def test_fmt_workout_detail_shape(self):
        data = {
            "id": "22398584",
            "prescribedDate": "2026-07-20",
            "title": "Supersets",
            "workoutType": "StructuredStrength",
            "instructions": None,
            "prescribedDurationInSeconds": 2400,
            "executedDurationInSeconds": 2612,
            "complianceState": "Compliant",
            "compliancePercent": 100.0,
            "rpe": 4,
            "feel": 5,
            "snapshot": {"totalSets": 30, "completedSets": 30},
            "blocks": [
                {
                    "blockType": "Superset",
                    "title": "Superset 1",
                    "coachNotes": None,
                    "compliancePercent": 100.0,
                    "prescriptions": [
                        {
                            "exercise": {"title": "Goblet Squat", "videoUrl": "http://v"},
                            "coachNotes": "go deep",
                            "compliancePercent": 100.0,
                            "sets": [
                                {"isComplete": True, "parameterValues": [
                                    {"parameter": "Reps", "prescribedValue": "10", "executedValue": "10"},
                                    {"parameter": "WeightLb", "prescribedValue": "45", "executedValue": "45"},
                                ]},
                            ],
                        }
                    ],
                }
            ],
        }
        out = _fmt_workout_detail(data)
        assert out["workout_id"] == "22398584"
        assert out["prescribed_duration_min"] == 40.0
        assert out["executed_duration_min"] == 43.5
        assert out["rpe"] == 4 and out["feel"] == 5
        assert out["total_sets"] == 30 and out["completed_sets"] == 30
        block = out["blocks"][0]
        assert block["type"] == "Superset"
        ex = block["exercises"][0]
        assert ex["exercise"] == "Goblet Squat"
        assert ex["video_url"] == "http://v"
        assert ex["sets"][0]["prescribed"] == {"Reps": "10", "WeightLb": "45"}


class TestListAndDetail:
    @pytest.mark.asyncio
    async def test_list_success(self):
        # Endpoint returns a bare JSON array.
        items = [
            {"id": "2", "prescribedDate": "2026-07-20", "title": "B", "workoutType": "StructuredStrength",
             "prescribedDurationInSeconds": 2400, "complianceState": "Compliant", "compliancePercent": 100.0,
             "totalSets": 30, "completedSets": 30,
             "sequenceSummary": [{"title": "Warm Up"}, {"title": "Pull Up"}]},
            {"id": "1", "prescribedDate": "2026-07-13", "title": "A", "workoutType": "StructuredStrength",
             "prescribedDurationInSeconds": 2100, "complianceState": "Compliant", "compliancePercent": 100.0,
             "totalSets": 20, "completedSets": 20, "sequenceSummary": []},
        ]
        http = _mock_http(200, items)
        with patch("tp_mcp.tools.strength.TPClient") as mtp:
            mtp.return_value.__aenter__.return_value = _mock_tp_client()
            with patch("tp_mcp.tools.strength.httpx.AsyncClient") as mh:
                mh.return_value.__aenter__.return_value = http
                r = await tp_get_strength_workouts(start_date="2026-07-01", end_date="2026-07-22")
        assert r["count"] == 2
        # Sorted ascending by date regardless of API order.
        assert [w["date"] for w in r["workouts"]] == ["2026-07-13", "2026-07-20"]
        assert r["workouts"][1]["exercises"] == ["Warm Up", "Pull Up"]
        assert r["workouts"][1]["prescribed_duration_min"] == 40.0

    @pytest.mark.asyncio
    async def test_list_requires_dates(self):
        r = await tp_get_strength_workouts(start_date="", end_date="2026-07-22")
        assert r["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_list_auth_failure(self):
        with patch("tp_mcp.tools.strength.TPClient") as mtp:
            mtp.return_value.__aenter__.return_value = _mock_tp_client(athlete_id=None)
            r = await tp_get_strength_workouts(start_date="2026-07-01", end_date="2026-07-22")
        assert r["error_code"] == "AUTH_INVALID"

    @pytest.mark.asyncio
    async def test_list_expired_session(self):
        http = _mock_http(401, {})
        with patch("tp_mcp.tools.strength.TPClient") as mtp:
            mtp.return_value.__aenter__.return_value = _mock_tp_client()
            with patch("tp_mcp.tools.strength.httpx.AsyncClient") as mh:
                mh.return_value.__aenter__.return_value = http
                r = await tp_get_strength_workouts(start_date="2026-07-01", end_date="2026-07-22")
        assert r["error_code"] == "AUTH_EXPIRED"

    @pytest.mark.asyncio
    async def test_detail_success(self):
        data = {"id": "22398584", "prescribedDate": "2026-07-20", "title": "Supersets",
                "workoutType": "StructuredStrength", "snapshot": {"totalSets": 30, "completedSets": 30},
                "blocks": []}
        http = _mock_http(200, {"data": data, "errors": {}})
        with patch("tp_mcp.tools.strength.TPClient") as mtp:
            mtp.return_value.__aenter__.return_value = _mock_tp_client()
            with patch("tp_mcp.tools.strength.httpx.AsyncClient") as mh:
                mh.return_value.__aenter__.return_value = http
                r = await tp_get_strength_workout(workout_id="22398584")
        assert r["workout_id"] == "22398584"
        assert r["blocks"] == []

    @pytest.mark.asyncio
    async def test_detail_not_found(self):
        http = _mock_http(404, {"message": "nope"})
        with patch("tp_mcp.tools.strength.TPClient") as mtp:
            mtp.return_value.__aenter__.return_value = _mock_tp_client()
            with patch("tp_mcp.tools.strength.httpx.AsyncClient") as mh:
                mh.return_value.__aenter__.return_value = http
                r = await tp_get_strength_workout(workout_id="999")
        assert r["error_code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_detail_auth_failure(self):
        with patch("tp_mcp.tools.strength.TPClient") as mtp:
            mtp.return_value.__aenter__.return_value = _mock_tp_client(athlete_id=None)
            r = await tp_get_strength_workout(workout_id="1")
        assert r["error_code"] == "AUTH_INVALID"

    @pytest.mark.asyncio
    async def test_detail_empty_data_is_not_found(self):
        http = _mock_http(200, {"data": None, "errors": {}})
        with patch("tp_mcp.tools.strength.TPClient") as mtp:
            mtp.return_value.__aenter__.return_value = _mock_tp_client()
            with patch("tp_mcp.tools.strength.httpx.AsyncClient") as mh:
                mh.return_value.__aenter__.return_value = http
                r = await tp_get_strength_workout(workout_id="999")
        assert r["error_code"] == "NOT_FOUND"
