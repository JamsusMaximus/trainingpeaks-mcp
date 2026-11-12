"""Tests for the heat block of tp_analyze_workout (tp_mcp.tools.heat) and tp_get_heat_sessions."""

import pytest

from tp_mcp.tools import heat_sessions
from tp_mcp.tools.heat import MIN_SAMPLES, heat_summary, htl_estimate
from tp_mcp.tools.heat_sessions import tp_get_heat_sessions


def _row(t, core, hsi=None, skin=33.0, hr=None, power=None, speed=None, ambient=None, quality=20):
    row = {"time": t, "CoreTemperature": core, "CoreDataQuality": quality}
    for key, value in (("HeatStrainIndex", hsi), ("SkinTemperature", skin), ("HeartRate", hr),
                       ("Power", power), ("Speed", speed), ("Temperature", ambient)):
        if value is not None:
            row[key] = value
    return row


def test_none_without_core_data():
    assert heat_summary([{"time": t, "Power": 200} for t in range(600)]) is None
    assert heat_summary([_row(t, 38.0) for t in range(MIN_SAMPLES - 1)]) is None


def test_artefacts_outside_body_range_ignored():
    rows = [_row(t, 0.0) for t in range(100)] + [_row(100 + t, 38.0) for t in range(60)]
    s = heat_summary(rows)
    assert s["core_temp_c"]["avg"] == 38.0 and s["minutes_with_core_data"] == 1.0


def test_core_start_end_rise_and_thresholds():
    # 10 min at 37.8, then 20 min at 38.6, then 10 min at 39.1 (1 s samples)
    rows = [_row(t, 37.8) for t in range(600)] + [_row(600 + t, 38.6) for t in range(1200)]
    rows += [_row(1800 + t, 39.1) for t in range(600)]
    core = heat_summary(rows)["core_temp_c"]
    assert core["start"] == 37.8 and core["end"] == 39.1 and core["max"] == 39.1
    assert core["rise"] == pytest.approx(1.3)
    assert core["minutes_at_or_above"] == {"38.0": 30.0, "38.5": 30.0, "39.0": 10.0}


def test_hsi_zones_and_time_to_zone3():
    # CORE Heat Zones: 1 = 0-0.9, 2 = 1-2.9, 3 = 3-6.9, 4 = 7+
    rows = [_row(t, 38.0, hsi=0.5) for t in range(300)] + [_row(300 + t, 38.3, hsi=2.0) for t in range(300)]
    rows += [_row(600 + t, 38.7, hsi=4.5) for t in range(1800)] + [_row(2400 + t, 39.3, hsi=7.2) for t in range(60)]
    hsi = heat_summary(rows)["heat_strain_index"]
    assert hsi["minutes_in_zone"] == {"zone1": 5.0, "zone2": 5.0, "zone3": 30.0, "zone4": 1.0}
    assert hsi["minutes_to_zone3"] == 10.0 and hsi["max"] == 7.2


def test_zone_boundaries_follow_core():
    rows = [_row(t, 38.0, hsi=h) for t, h in enumerate([0.9, 1.0, 2.9, 3.0, 6.9, 7.0] * 10)]
    zones = heat_summary(rows)["heat_strain_index"]["minutes_in_zone"]
    assert zones == {"zone1": round(10 / 60, 1), "zone2": round(20 / 60, 1), "zone3": round(20 / 60, 1),
                     "zone4": round(10 / 60, 1)}


def test_skin_gradient_ambient_and_segments():
    rows = [_row(t, 38.0 + t / 3600, hsi=3.0, skin=33.0, hr=140 + t // 900, power=200, ambient=30.0)
            for t in range(3600)]
    s = heat_summary(rows)
    assert s["skin_temp_c"]["avg"] == 33.0
    assert s["skin_temp_c"]["core_skin_gradient_avg"] == pytest.approx(5.5, abs=0.01)
    assert s["ambient_temp_c"] == {"avg": 30.0, "max": 30.0}
    segs = s["by_segment"]
    assert [g["hr_avg"] for g in segs] == [140, 141, 142, 143]
    assert segs[0]["core_avg"] < segs[-1]["core_avg"] and segs[0]["power_avg_w"] == 200
    assert "speed_avg_kmh" not in segs[0]


def test_run_segments_show_speed_and_downsample_note():
    rows = [_row(t * 18, 38.5, hsi=3.5, speed=11.8) for t in range(100)]  # km/h as delivered by TP
    s = heat_summary(rows)
    assert s["by_segment"][0]["speed_avg_kmh"] == 11.8
    assert s["sample_spacing_s"] == 18.0 and "downsampled" in s["note"]


def test_quality_reported():
    rows = [_row(t, 38.0, quality=20) for t in range(90)] + [_row(90 + t, 38.0, quality=16) for t in range(10)]
    assert heat_summary(rows)["core_data_quality"] == {"min": 16.0, "share_at_max_pct": 90.0}


# --- tp_get_heat_sessions

def _workouts(*items):
    return {"workouts": [{"id": i, "date": d, "sport": "Bike", "title": "T", "duration_actual": h, "tss_actual": 50}
                         for i, d, h in items]}


@pytest.fixture
def fake_api(monkeypatch):
    calls = {"analyze": []}

    async def get_workouts(start, end, workout_filter="all", compact=False):
        return calls["listing"]

    async def analyze(workout_id, timezone=None, *, light=False):
        calls["analyze"].append((workout_id, light))
        return calls["results"].get(workout_id, {"totals": {}})

    monkeypatch.setattr(heat_sessions, "tp_get_workouts", get_workouts)
    monkeypatch.setattr(heat_sessions, "tp_analyze_workout", analyze)
    return calls


def _heat(zone3):
    rows = [_row(t, 38.6, hsi=4.0, skin=34.0) for t in range(int(zone3 * 60))]
    return heat_summary(rows)


async def test_sessions_rows_and_summary(fake_api):
    fake_api["listing"] = _workouts((1, "2026-08-01", 1.0), (2, "2026-08-02", 1.0), (3, "2026-08-03", 0.1))
    fake_api["results"] = {
        "1": {"totals": {"Avg heart rate": {"value": 141}, "NP": {"value": 230}}, "heat": _heat(50)},
        "2": {"totals": {}},  # no CORE data
    }
    result = await tp_get_heat_sessions("2026-08-01", "2026-08-07")
    assert fake_api["analyze"] == [("1", True), ("2", True)]   # light mode; 6-min workout skipped
    row = result["sessions"][0]
    assert row["date"] == "2026-08-01" and row["hr_avg"] == 141.0 and row["np_w"] == 230.0
    assert row["zone_minutes"]["zone3"] == 50.0 and row["core_max_c"] == 38.6
    summary = result["summary"]
    assert summary["sessions_with_core_data"] == 1 and summary["zone3_minutes_total"] == 50.0
    assert summary["sessions_with_zone3_at_least_45_min"] == 1 and summary["zone4_minutes_total"] == 0.0
    assert summary["daily_htl_estimate"] == [{"date": "2026-08-01", "htl_estimate": row["htl_estimate"]}]
    assert row["htl_estimate"] == 7.6  # 50 min at HSI 4.0 -> column 4.5: 7.0 + (8.8 - 7.0) * 5 / 15
    assert summary["effective_sessions"] == 1 and summary["last_effective_session"] == "2026-08-01"
    assert summary["days_since_last_effective_session_at_end_date"] == 6
    assert result["workouts_without_core_data"] == 1 and "truncated" not in result


async def test_truncates_and_points_to_next_start(fake_api, monkeypatch):
    monkeypatch.setattr(heat_sessions, "MAX_WORKOUTS", 2)
    fake_api["listing"] = _workouts((1, "2026-08-01", 1.0), (2, "2026-08-02", 1.0), (3, "2026-08-05", 1.0))
    fake_api["results"] = {}
    result = await tp_get_heat_sessions("2026-08-01", "2026-08-07")
    assert result["truncated"] is True and result["next_start_date"] == "2026-08-05"
    assert len(fake_api["analyze"]) == 2


async def test_analysis_error_is_listed_not_fatal(fake_api):
    fake_api["listing"] = _workouts((1, "2026-08-01", 1.0), (2, "2026-08-02", 1.0))
    fake_api["results"] = {"1": {"isError": True, "error_code": "API_ERROR"}, "2": {"totals": {}, "heat": _heat(10)}}
    result = await tp_get_heat_sessions("2026-08-01", "2026-08-07")
    assert result["errors"] == [{"workout_id": "1", "error": "API_ERROR"}] and len(result["sessions"]) == 1


@pytest.mark.parametrize("start, end", [("2026-08-07", "2026-08-01"), ("2026-01-01", "2026-06-01"), ("x", "y")])
async def test_invalid_range(fake_api, start, end):
    result = await tp_get_heat_sessions(start, end)
    assert result["isError"] and result["error_code"] == "VALIDATION_ERROR" and fake_api["analyze"] == []


# --- Heat Training Load estimate (CORE table)

def _hsi_session(levels):
    values = []
    for minutes, hsi in levels:
        values += [hsi] * (minutes * 60)
    return htl_estimate(values, 1.0)


@pytest.mark.parametrize("levels, expected", [
    ([(60, 4.5)], 8.8), ([(30, 3.5)], 4.0), ([(45, 5.5)], 7.9), ([(60, 6.5)], 10.0),
    ([(180, 2.5)], 7.3), ([(180, 1.5)], 1.4), ([(180, 0.8)], 0.0), ([(120, 6.0)], 10.0),
])
def test_htl_reproduces_core_table(levels, expected):
    assert _hsi_session(levels) == expected


def test_htl_close_to_core_examples():
    ramp = [(5, 0.5), (5, 1.5), (10, 2.5), (5, 3.2)]
    assert abs(_hsi_session(ramp + [(60, 4.5)]) - 8.7) <= 0.3   # CORE example 1a
    assert abs(_hsi_session([(30, 0.7), (60, 2.3)]) - 2.4) <= 0.3  # CORE example 6


def test_daily_htl_adds_sessions_and_caps():
    rows = [{"date": "2026-08-01", "htl_estimate": 6.0}, {"date": "2026-08-01", "htl_estimate": 5.5},
            {"date": "2026-08-02", "htl_estimate": 2.0}]
    assert heat_sessions._daily_htl(rows) == [{"date": "2026-08-01", "htl_estimate": 10.0},
                                              {"date": "2026-08-02", "htl_estimate": 2.0}]


def test_effective_sessions_and_gaps():
    rows = [{"date": d, "zone_minutes": {"zone3": z}} for d, z in
            [("2026-08-01", 50), ("2026-08-03", 30), ("2026-08-05", 60), ("2026-08-12", 45)]]
    eff = heat_sessions._effective_sessions(rows, "2026-08-20")
    assert eff["effective_session_dates"] == ["2026-08-01", "2026-08-05", "2026-08-12"]
    assert eff["longest_gap_days_between_effective_sessions"] == 7
    assert eff["days_since_last_effective_session_at_end_date"] == 8
    assert heat_sessions._effective_sessions([], "2026-08-20") == {"effective_sessions": 0}


def test_safety_warnings():
    rows = [_row(t, 39.2, hsi=7.5) for t in range(120)] + [_row(120 + t, 38.6, hsi=4.0) for t in range(110 * 60)]
    warnings = heat_summary(rows)["safety_warnings"]
    assert any("core at or above 39" in w for w in warnings)
    assert any("Zone 4" in w for w in warnings) and any("100 min maximum" in w for w in warnings)
    assert "safety_warnings" not in heat_summary([_row(t, 38.5, hsi=4.0) for t in range(3600)])


def test_hsi_without_skin_temperature_is_marked_unusable():
    # Indoor recording: core 38.6 C, HSI near 0, no skin channel (real case)
    rows = [_row(t, 38.6, hsi=0.4, skin=None) for t in range(3600)]
    s = heat_summary(rows)
    hsi = s["heat_strain_index"]
    assert hsi["reliable"] is False and "minutes_in_zone" not in hsi and "heat_training_load_estimate" not in hsi
    assert s["core_temp_c"]["minutes_at_or_above"]["38.5"] == 60.0


async def test_sessions_flag_unusable_hsi(fake_api):
    fake_api["listing"] = _workouts((1, "2026-09-15", 1.5))
    no_skin = heat_summary([_row(t, 38.6, hsi=0.4, skin=None) for t in range(5400)])
    fake_api["results"] = {"1": {"totals": {}, "heat": no_skin}}
    result = await tp_get_heat_sessions("2026-09-15", "2026-09-20")
    row = result["sessions"][0]
    assert row["hsi_unusable_no_skin_temp"] is True and "htl_estimate" not in row
    assert row["core_min_at_or_above_38_0"] == 90.0
    assert result["summary"]["sessions_hsi_unusable_no_skin_temp"] == ["2026-09-15"]
    assert result["summary"]["daily_htl_estimate"] == []
