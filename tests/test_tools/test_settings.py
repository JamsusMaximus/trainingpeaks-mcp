"""Tests for athlete settings zone tools (method-agnostic, per-sport)."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools.settings import (
    _parse_pace_to_ms,
    _rescaled_group,
    _select_group_index,
    tp_get_athlete_settings,
    tp_update_ftp,
    tp_update_hr_zones,
    tp_update_nutrition,
    tp_update_speed_zones,
)

_OK = APIResponse(success=True, data=None)


def _client(settings, calc_zones=None):
    """Patched TPClient: GET returns `settings`, PUT succeeds. `calc_zones` (if
    given) is returned by the zone-calculator POST (method-correct path);
    otherwise the calculator returns no zones and the code falls back to the
    proportional rescale. Returns (patcher, mock_instance)."""
    p = patch("tp_mcp.tools.settings.TPClient")
    mock_client = p.start()
    mi = AsyncMock()
    mi.ensure_athlete_id = AsyncMock(return_value=123)
    mi._get_user_data = AsyncMock(return_value={"userId": 1135463})
    mi.get = AsyncMock(return_value=APIResponse(success=True, data=settings))
    mi.put = AsyncMock(return_value=_OK)
    calc_data = {"zones": calc_zones} if calc_zones is not None else {}
    mi.post = AsyncMock(return_value=APIResponse(success=True, data=calc_data))
    mock_client.return_value.__aenter__.return_value = mi
    return p, mi


def _pzones(thr, wtid, method, n=6, ceiling=2000):
    step = thr // n
    zones = [{"label": str(i + 1), "minimum": i * step, "maximum": (i + 1) * step} for i in range(n)]
    zones[-1]["maximum"] = ceiling
    return {"zoneCalculatorId": None, "threshold": thr, "calculationMethod": method,
            "workoutTypeId": wtid, "zones": zones}


# ── pure helpers ──────────────────────────────────────────────────────────────

def test_select_group_index_exact_then_fallback():
    groups = [{"workoutTypeId": 0}, {"workoutTypeId": 2}]
    assert _select_group_index(groups, 2) == (1, None)
    idx, note = _select_group_index(groups, 3)          # missing → default(0)
    assert idx == 0 and "default" in note
    idx2, note2 = _select_group_index([{"workoutTypeId": 5}], 3)  # no default → first
    assert idx2 == 0 and note2


def test_rescaled_group_preserves_all_fields_and_ceiling():
    g = {"threshold": 200, "calculationMethod": 7, "distance": 5, "zoneCalculatorId": "x",
         "workoutTypeId": 1, "zones": [{"label": "Z1", "minimum": 0, "maximum": 100},
                                       {"label": "Z2", "minimum": 101, "maximum": 1000}]}
    new, err = _rescaled_group(g, 220, integer=True)
    assert err is None
    assert new["calculationMethod"] == 7 and new["distance"] == 5 and new["zoneCalculatorId"] == "x"
    assert new["threshold"] == 220
    assert new["zones"][0]["maximum"] == 110          # 100 * 1.1
    assert new["zones"][-1]["maximum"] == 1000        # ceiling preserved (not scaled)


def test_rescaled_group_rejects_zero_and_malformed():
    assert _rescaled_group({"threshold": 0, "zones": []}, 200, integer=True)[0] is None
    bad = {"threshold": 200, "zones": [{"maximum": "x"}, {"maximum": 1000}]}
    assert _rescaled_group(bad, 220, integer=True)[0] is None


# ── get / nutrition (unchanged) ───────────────────────────────────────────────

class TestGetAthleteSettings:
    @pytest.mark.asyncio
    async def test_success(self):
        p, _ = _client({"threshold": 280, "zones": []})
        try:
            result = await tp_get_athlete_settings()
        finally:
            p.stop()
        assert "settings" in result


class TestUpdateNutrition:
    @pytest.mark.asyncio
    async def test_success(self):
        with patch("tp_mcp.tools.settings.TPClient") as mock_client:
            mi = AsyncMock()
            mi.ensure_athlete_id = AsyncMock(return_value=123)
            mi.post = AsyncMock(return_value=_OK)
            mock_client.return_value.__aenter__.return_value = mi
            result = await tp_update_nutrition(planned_calories=2500)
        assert result["success"] is True and result["planned_calories"] == 2500


# ── FTP ───────────────────────────────────────────────────────────────────────

class TestUpdateFTP:
    @pytest.mark.asyncio
    async def test_targets_bike_set_and_preserves_method(self):
        settings = {"powerZones": [_pzones(280, 0, 5), _pzones(250, 2, 1)]}
        p, mi = _client(settings)
        try:
            result = await tp_update_ftp(ftp=300, workout_type="bike")
        finally:
            p.stop()
        assert result["success"] and result["workout_type_id"] == 2
        assert result["calculation_method"] == 1 and result["method_correct"] is False
        payload = mi.put.call_args[1]["json"]
        assert payload[1]["threshold"] == 300 and payload[1]["workoutTypeId"] == 2
        assert payload[0] == settings["powerZones"][0]   # default set untouched

    @pytest.mark.asyncio
    async def test_default_bike_falls_back_to_default_set(self):
        settings = {"powerZones": [_pzones(280, 0, 5)]}   # no bike set
        p, mi = _client(settings)
        try:
            result = await tp_update_ftp(ftp=320)          # default workout_type="bike"
        finally:
            p.stop()
        assert result["success"] and result["workout_type_id"] == 0 and result.get("note")
        zones = result["zones"]
        assert zones[0]["maximum"] == round(settings["powerZones"][0]["zones"][0]["maximum"] * 320 / 280)
        assert zones[-1]["maximum"] == 2000              # ceiling preserved

    @pytest.mark.asyncio
    async def test_coggan_fallback_on_zero_threshold(self):
        settings = {"powerZones": [_pzones(0, 0, 5)]}
        p, _ = _client(settings)
        try:
            result = await tp_update_ftp(ftp=200, workout_type="default")
        finally:
            p.stop()
        assert result["success"]
        assert result["zones"][0]["maximum"] == round(200 * 0.56)
        assert result["zones"][-1]["maximum"] == 2000

    @pytest.mark.asyncio
    async def test_coggan_fallback_on_malformed(self):
        s = _pzones(280, 0, 5)
        s["zones"][0]["maximum"] = "bad"
        p, _ = _client({"powerZones": [s]})
        try:
            result = await tp_update_ftp(ftp=300, workout_type="default")
        finally:
            p.stop()
        assert result["success"] and result["zones"][0]["maximum"] == round(300 * 0.56)

    @pytest.mark.asyncio
    async def test_targets_xcski_power_set(self):
        # wtid 11 = XCSki (from the connector's SPORT_TYPE_MAP) — power zones for
        # skiing must be settable, not just bike/run.
        settings = {"powerZones": [_pzones(280, 0, 5), _pzones(200, 11, 5)]}
        p, mi = _client(settings)
        try:
            result = await tp_update_ftp(ftp=210, workout_type="xcski")
        finally:
            p.stop()
        assert result["success"] and result["workout_type_id"] == 11
        payload = mi.put.call_args[1]["json"]
        assert payload[1]["threshold"] == 210 and payload[1]["workoutTypeId"] == 11
        assert payload[0] == settings["powerZones"][0]   # default untouched

    @pytest.mark.asyncio
    async def test_validation(self):
        assert (await tp_update_ftp(ftp=0))["error_code"] == "VALIDATION_ERROR"


# ── HR ────────────────────────────────────────────────────────────────────────

def _hzones(thr, wtid, method):
    return {"zoneCalculatorId": None, "threshold": thr, "maximumHeartRate": 190,
            "restingHeartRate": 50, "calculationMethod": method, "workoutTypeId": wtid,
            "zones": [{"label": f"Z{i}", "minimum": 100 + i * 10, "maximum": 110 + i * 10}
                      for i in range(7)]}


class TestUpdateHRZones:
    @pytest.mark.asyncio
    async def test_threshold_preserves_method_and_anchors(self):
        settings = {"heartRateZones": [_hzones(160, 0, 3)]}
        p, mi = _client(settings)
        try:
            result = await tp_update_hr_zones(threshold_hr=170)   # general → wtid 0
        finally:
            p.stop()
        assert result["success"] and result["calculation_method"] == 3
        payload = mi.put.call_args[1]["json"]
        assert isinstance(payload, list) and payload[0]["threshold"] == 170
        assert payload[0]["calculationMethod"] == 3            # method preserved
        assert payload[0]["maximumHeartRate"] == 190           # anchor preserved

    @pytest.mark.asyncio
    async def test_targets_run_set(self):
        settings = {"heartRateZones": [_hzones(160, 0, 3), _hzones(165, 3, 2)]}
        p, mi = _client(settings)
        try:
            result = await tp_update_hr_zones(threshold_hr=175, workout_type="run")
        finally:
            p.stop()
        assert result["workout_type_id"] == 3 and result["calculation_method"] == 2
        payload = mi.put.call_args[1]["json"]
        assert payload[1]["threshold"] == 175
        assert payload[0] == settings["heartRateZones"][0]     # default untouched

    @pytest.mark.asyncio
    async def test_max_only_keeps_threshold_and_bands(self):
        settings = {"heartRateZones": [_hzones(160, 0, 3)]}
        before = [(z["minimum"], z["maximum"]) for z in settings["heartRateZones"][0]["zones"]]
        p, mi = _client(settings)
        try:
            result = await tp_update_hr_zones(max_hr=195)
        finally:
            p.stop()
        assert result["success"]
        payload = mi.put.call_args[1]["json"]
        assert payload[0]["threshold"] == 160                  # unchanged
        assert payload[0]["maximumHeartRate"] == 195           # updated anchor
        after = [(z["minimum"], z["maximum"]) for z in payload[0]["zones"]]
        assert after == before                                 # bands unchanged
        assert "recompute in TP" in result.get("note", "")  # method-aware warning (fallback)

    @pytest.mark.asyncio
    async def test_no_params_rejected(self):
        assert (await tp_update_hr_zones())["isError"] is True

    @pytest.mark.asyncio
    async def test_invalid_workout_type_rejected(self):
        assert (await tp_update_hr_zones(threshold_hr=160, workout_type="xc"))["error_code"] == "VALIDATION_ERROR"


# ── Speed / pace (incl. Distance-Time preservation) ───────────────────────────

def _szones(thr, wtid, method, distance):
    return {"zoneCalculatorId": None, "threshold": thr, "calculationMethod": method,
            "distance": distance, "workoutTypeId": wtid,
            "zones": [{"label": f"Z{i}", "minimum": thr * (0.3 + 0.1 * i),
                       "maximum": thr * (0.4 + 0.1 * i)} for i in range(7)]}


class TestUpdateSpeedZones:
    def test_parse_run_pace(self):
        assert abs(_parse_pace_to_ms("4:30/km") - 3.704) < 0.01

    def test_parse_swim_pace(self):
        assert abs(_parse_pace_to_ms("1:45/100m", is_swim=True) - 0.952) < 0.01

    def test_parse_pace_honours_unit(self):
        import pytest as _pytest
        assert abs(_parse_pace_to_ms("5:00/mi") - 1609.344 / 300) < 0.01      # miles
        assert abs(_parse_pace_to_ms("1:50/100yd", is_swim=True) - 91.44 / 110) < 0.01
        with _pytest.raises(ValueError):
            _parse_pace_to_ms("5:00/furlong")                                  # unknown unit

    @pytest.mark.asyncio
    async def test_run_preserves_method_and_distance(self):
        settings = {"speedZones": [_szones(3.7, 3, 2, 0)]}
        p, mi = _client(settings)
        try:
            result = await tp_update_speed_zones(run_threshold_pace="4:30/km")
        finally:
            p.stop()
        assert result["success"]
        upd = result["updated"][0]
        assert upd["sport"] == "run" and upd["workout_type_id"] == 3
        assert upd["calculation_method"] == 2 and upd["distance"] == 0
        payload = mi.put.call_args[1]["json"]
        assert abs(payload[0]["threshold"] - 3.704) < 0.01

    @pytest.mark.asyncio
    async def test_swim_distance_time_set_is_preserved(self):
        # The user's concern: a swim set on Distance/Time (method 3, distance>0)
        # must keep its method AND distance when only the threshold pace changes.
        settings = {"speedZones": [_szones(3.7, 3, 2, 0), _szones(0.83, 1, 3, 5)]}
        p, mi = _client(settings)
        try:
            result = await tp_update_speed_zones(swim_threshold_pace="1:45/100m")
        finally:
            p.stop()
        upd = result["updated"][0]
        assert upd["sport"] == "swim" and upd["workout_type_id"] == 1
        assert upd["calculation_method"] == 3 and upd["distance"] == 5   # Distance/Time intact
        payload = mi.put.call_args[1]["json"]
        assert payload[1]["calculationMethod"] == 3 and payload[1]["distance"] == 5
        assert payload[0] == settings["speedZones"][0]                   # run set untouched

    @pytest.mark.asyncio
    async def test_run_and_swim_single_put(self):
        settings = {"speedZones": [_szones(3.7, 3, 2, 0), _szones(0.83, 1, 3, 5)]}
        p, mi = _client(settings)
        try:
            result = await tp_update_speed_zones(run_threshold_pace="4:30/km",
                                                 swim_threshold_pace="1:45/100m")
        finally:
            p.stop()
        assert len(result["updated"]) == 2
        assert mi.put.await_count == 1                                   # both in ONE PUT

    @pytest.mark.asyncio
    async def test_invalid_pace_format(self):
        assert (await tp_update_speed_zones(run_threshold_pace="invalid"))["isError"] is True

    @pytest.mark.asyncio
    async def test_no_params_rejected(self):
        assert (await tp_update_speed_zones())["isError"] is True


# ── Method-correct path: TP zone calculator ──────────────────────────────────

class TestCalculatePath:
    @pytest.mark.asyncio
    async def test_ftp_uses_calculator_when_available(self):
        settings = {"powerZones": [_pzones(280, 0, 5), _pzones(250, 2, 1)]}
        calc = [{"label": str(i + 1), "minimum": i, "maximum": (i + 1) * 50} for i in range(6)]
        p, mi = _client(settings, calc_zones=calc)
        try:
            result = await tp_update_ftp(ftp=300, workout_type="bike")
        finally:
            p.stop()
        assert result["success"] and result["method_correct"] is True
        # calculator output is used verbatim (mapped), NOT a proportional rescale
        payload = mi.put.call_args[1]["json"]
        assert payload[1]["zones"] == calc and payload[1]["threshold"] == 300
        # calculator POST was hit with the set's method as zoneType
        call = mi.post.call_args
        assert "/power/calculate/1" in call[0][0]
        assert call[1]["json"]["LTPower"] == 300 and call[1]["json"]["zoneType"] == 1

    @pytest.mark.asyncio
    async def test_hr_max_based_method_recomputed_by_calculator(self):
        # The case proportional rescale gets WRONG: a max-based HR set. With the
        # calculator, changing max_hr recomputes bands method-correctly.
        settings = {"heartRateZones": [_hzones(160, 0, 3)]}
        calc = [{"label": f"Z{i}", "minimum": i * 20, "maximum": (i + 1) * 20} for i in range(7)]
        p, mi = _client(settings, calc_zones=calc)
        try:
            result = await tp_update_hr_zones(max_hr=195)   # no threshold change
        finally:
            p.stop()
        assert result["method_correct"] is True
        payload = mi.put.call_args[1]["json"]
        assert payload[0]["zones"] == calc                  # bands recomputed, not stale
        assert payload[0]["maximumHeartRate"] == 195
        body = mi.post.call_args[1]["json"]
        assert body["maxHR"] == 195 and body["LTHR"] == 160  # both anchors sent

    @pytest.mark.asyncio
    async def test_swim_distance_time_calculator_keeps_distance(self):
        settings = {"speedZones": [_szones(0.83, 1, 3, 5)]}
        calc = [{"label": f"Z{i}", "minimumAsDouble": i * 0.1, "maximumAsDouble": (i + 1) * 0.1}
                for i in range(7)]
        p, mi = _client(settings, calc_zones=calc)
        try:
            result = await tp_update_speed_zones(swim_threshold_pace="1:45/100m")
        finally:
            p.stop()
        upd = result["updated"][0]
        assert upd["method_correct"] is True and upd["distance"] == 5
        body = mi.post.call_args[1]["json"]
        assert body["zoneType"] == 3 and body["distance"] == 5   # Distance/Time preserved
        assert "speed" in body

    @pytest.mark.asyncio
    async def test_test_based_method_is_refused_not_silently_wrong(self):
        # Distance/Time: the calculator DERIVES a threshold from the input (as a
        # test result), far from what was asked. The connector must REFUSE rather
        # than silently store a threshold the coach didn't intend, and write nothing.
        settings = {"speedZones": [_szones(0.83, 1, 3, 5)]}
        with patch("tp_mcp.tools.settings.TPClient") as mc:
            mi = AsyncMock()
            mi.ensure_athlete_id = AsyncMock(return_value=123)
            mi._get_user_data = AsyncMock(return_value={"userId": 1})
            mi.get = AsyncMock(return_value=APIResponse(success=True, data=settings))
            mi.put = AsyncMock(return_value=_OK)
            calc = [{"label": f"Z{i}", "minimumAsDouble": i * 0.1, "maximumAsDouble": (i + 1) * 0.1}
                    for i in range(7)]
            # input 1:45/100m ≈ 0.952 m/s, but calculator derives 0.60 (test-based)
            mi.post = AsyncMock(return_value=APIResponse(
                success=True, data={"zones": calc, "thresholdSpeed": 0.60}))
            mc.return_value.__aenter__.return_value = mi
            result = await tp_update_speed_zones(swim_threshold_pace="1:45/100m")
        assert result["error_code"] == "TEST_BASED_METHOD"
        mi.put.assert_not_called()                       # nothing written


# ── tp_create_zones (new per-sport set) ──────────────────────────────────────

import pytest as _pytest  # noqa: E402
from tp_mcp.tools.settings import tp_create_zones  # noqa: E402

_CALC7 = [{"label": str(i + 1), "minimum": i, "maximum": i + 1,
           "minimumAsDouble": float(i), "maximumAsDouble": float(i + 1)} for i in range(7)]


@_pytest.mark.asyncio
async def test_create_zones_power_builds_new_group():
    # athlete has only the default (wtid 0) power set → bike (wtid 2) is absent
    settings = {"powerZones": [_pzones(250, 0, 1)]}
    p, mi = _client(settings, calc_zones=_CALC7)
    try:
        out = await tp_create_zones(metric="power", workout_type="bike",
                                    calculation_method=4, threshold=260)
    finally:
        p.stop()
    assert out["success"] and out["created"]
    assert out["workout_type_id"] == 2 and out["calculation_method"] == 4
    # PUT received the full array INCLUDING the new wtid-2 group
    put_body = mi.put.call_args[1]["json"] if mi.put.call_args[1] else mi.put.call_args[0][1]
    assert {g["workoutTypeId"] for g in put_body} == {0, 2}
    new = next(g for g in put_body if g["workoutTypeId"] == 2)
    assert new["calculationMethod"] == 4 and new["threshold"] == 260 and len(new["zones"]) == 7


@_pytest.mark.asyncio
async def test_create_zones_refuses_when_set_exists():
    settings = {"powerZones": [_pzones(250, 2, 4)]}   # bike set already present
    p, _ = _client(settings, calc_zones=_CALC7)
    try:
        out = await tp_create_zones(metric="power", workout_type="bike",
                                    calculation_method=4, threshold=260)
    finally:
        p.stop()
    assert out["isError"] and out["error_code"] == "ZONES_EXIST"


@_pytest.mark.asyncio
async def test_create_zones_speed_needs_pace():
    p, _ = _client({"speedZones": []}, calc_zones=_CALC7)
    try:
        out = await tp_create_zones(metric="speed", workout_type="run",
                                    calculation_method=2)
    finally:
        p.stop()
    assert out["isError"] and out["error_code"] == "VALIDATION_ERROR"


@_pytest.mark.asyncio
async def test_create_zones_speed_from_pace():
    p, mi = _client({"speedZones": []}, calc_zones=_CALC7)
    try:
        out = await tp_create_zones(metric="speed", workout_type="run",
                                    calculation_method=2, pace="4:00/km")
    finally:
        p.stop()
    assert out["success"] and out["workout_type_id"] == 3
    put_body = mi.put.call_args[1]["json"] if mi.put.call_args[1] else mi.put.call_args[0][1]
    new = next(g for g in put_body if g["workoutTypeId"] == 3)
    assert new["calculationMethod"] == 2 and len(new["zones"]) == 7
