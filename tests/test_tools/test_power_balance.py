"""Tests for left/right power balance analysis."""

import gzip

import pytest

from tp_mcp.fit import WorkoutDataPoint, bucket_left_right_power, decode_left_right_balance, format_power_buckets
from tp_mcp.tools.power_balance import tp_analyze_power_balance


def _pt(power, balance):
    return WorkoutDataPoint(power=power, left_right_balance=balance)


def test_decode_balance_left_and_right_flag():
    assert decode_left_right_balance(48, 200) == {
        "left_pct": 48, "right_pct": 52, "left_watts": 96.0, "right_watts": 104.0,
    }
    assert decode_left_right_balance(0x80 | 48)["right_pct"] == 48


def test_bucketing_skips_unusable_and_groups():
    pts = [_pt(210, 50), _pt(240, 50), _pt(None, 50), _pt(100, None), _pt(60, 50)]
    buckets = bucket_left_right_power(pts, 50)
    assert buckets[(200, 250)]["datapoints"] == 2
    assert buckets[(50, 100)]["datapoints"] == 1
    assert buckets[(0, 50)]["datapoints"] == 0
    assert "Left 50.00% / Right 50.00%" in format_power_buckets(buckets, 1)


def test_bucket_size_validation():
    with pytest.raises(ValueError):
        bucket_left_right_power([], 0)


async def test_tool_validation_and_missing_file(tmp_path):
    assert (await tp_analyze_power_balance([]))["isError"]
    assert (await tp_analyze_power_balance(["x"], bucket_size=0))["isError"]
    res = await tp_analyze_power_balance([str(tmp_path / "nope.fit.gz")])
    assert res["isError"]


async def test_tool_corrupt_file_reported(tmp_path):
    bad = tmp_path / "bad.fit.gz"
    bad.write_bytes(gzip.compress(b"not a fit file"))
    res = await tp_analyze_power_balance([str(bad)])
    assert res["isError"]
