"""Tests for the pedaling block of tp_analyze_workout (tp_mcp.tools.pedaling)."""

from tp_mcp.tools.pedaling import MIN_SAMPLES, pedaling_summary


def _row(t, power, balance, cadence=90, te=(70, 75), ps=(20, 22)):
    return {"time": t, "Power": power, "LeftRightBalance": balance, "Cadence": cadence,
            "LeftTorqueEffectiveness": te[0], "RightTorqueEffectiveness": te[1],
            "LeftPedalSmoothness": ps[0], "RightPedalSmoothness": ps[1]}


def test_none_without_balance_data():
    rows = [{"time": t, "Power": 200, "Cadence": 90} for t in range(600)]
    assert pedaling_summary(rows) is None
    assert pedaling_summary([_row(t, 200, 50) for t in range(MIN_SAMPLES - 1)]) is None


def test_balance_is_power_weighted_and_ignores_coasting():
    # 100 s at 100 W with 40 % left, 100 s at 300 W with 50 % left, 50 s coasting (balance 0/100 artefacts)
    rows = [_row(t, 100, 40) for t in range(100)] + [_row(100 + t, 300, 50) for t in range(100)]
    rows += [_row(200 + t, 0, 0, cadence=0, te=(0, 0), ps=(0, 0)) for t in range(50)]
    rows += [_row(250 + t, 150, 100) for t in range(5)]          # one-legged artefact, excluded
    s = pedaling_summary(rows)
    assert s["left_pct"] == 47.5                                 # (100*40 + 300*50) / 400, not mean 45
    assert s["pedaling_minutes"] == round(200 / 60, 1)
    assert s["torque_effectiveness_pct"] == {"left": 70.0, "right": 75.0}   # zeros while coasting ignored
    assert s["pedal_smoothness_pct"] == {"left": 20.0, "right": 22.0}
    assert "note" not in s                                       # 1 s spacing


def test_by_power_buckets():
    rows = [_row(t, 120, 48) for t in range(60)] + [_row(60 + t, 320, 53) for t in range(120)]
    buckets = {tuple(b["range_w"]): b for b in pedaling_summary(rows)["by_power"]}
    assert buckets[(100, 150)] == {"range_w": [100, 150], "left_pct": 48.0, "minutes": 1.0}
    assert buckets[(300, 350)]["left_pct"] == 53.0 and buckets[(300, 350)]["minutes"] == 2.0


def test_by_segment_shows_drift():
    rows = [_row(t, 200, 50 - (t // 100)) for t in range(400)]  # left share drops 50 → 47
    segments = pedaling_summary(rows)["by_segment"]
    assert [s["left_pct"] for s in segments] == [50.0, 49.0, 48.0, 47.0]
    assert segments[0]["from_min"] == 0.0 and segments[-1]["to_min"] == round(399 / 60, 1)


def test_downsampled_series_is_flagged():
    rows = [_row(t * 18, 200, 50) for t in range(100)]
    s = pedaling_summary(rows)
    assert s["sample_spacing_s"] == 18.0 and "downsampled" in s["note"]
    assert s["pedaling_minutes"] == 30.0


def test_missing_cadence_channel_still_works():
    rows = [{"time": t, "Power": 200, "LeftRightBalance": 49} for t in range(60)]
    s = pedaling_summary(rows)
    assert s["left_pct"] == 49.0 and "torque_effectiveness_pct" not in s


async def test_analyze_workout_includes_pedaling(monkeypatch, tmp_path):
    from unittest.mock import AsyncMock, MagicMock, patch

    from tp_mcp.tools import analyze

    monkeypatch.setattr(analyze, "ANALYSIS_DATA_DIR", tmp_path / "analysis")
    rows = [_row(t, 200, 49) for t in range(120)]

    async def post(url, headers=None, json=None):
        resp = MagicMock()
        resp.status_code = 200
        if url.endswith("/summary"):
            resp.json.return_value = {"startTimestamp": "2026-10-10T07:00:00", "data": {}}
        elif url.endswith("/charts"):
            resp.json.return_value = {"metadata": {}, "data": rows}
        else:
            resp.json.return_value = {"columnMetadata": {}, "data": []}
        return resp

    client = AsyncMock()
    client.ensure_athlete_id = AsyncMock(return_value=1)
    client._ensure_access_token = AsyncMock(return_value=MagicMock(success=True))
    client._token_cache = MagicMock(access_token="t")
    http = AsyncMock()
    http.post = post
    with patch("tp_mcp.tools.analyze.TPClient") as tp, patch("tp_mcp.tools.analyze.httpx.AsyncClient") as hx:
        tp.return_value.__aenter__.return_value = client
        hx.return_value.__aenter__.return_value = http
        result = await analyze.tp_analyze_workout("123")
    assert result["pedaling"]["left_pct"] == 49.0
    assert result["pedaling"]["torque_effectiveness_pct"] == {"left": 70.0, "right": 75.0}
