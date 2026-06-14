"""Tests for tp_get_zone_methods — method discovery via the zone calculator."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools.zone_methods import tp_get_zone_methods


def _zones(labels):
    return [{"label": label, "minimum": 0, "maximum": 1} for label in labels]


def _client(responses):
    """Patch TPClient so calculate POSTs are answered from `responses`, keyed by
    (metric, method) → data dict (or None for an error/skip). _get_user_data
    returns a userId. Returns (patcher, mock_instance)."""
    p = patch("tp_mcp.tools.zone_methods.TPClient")
    mock_client = p.start()
    mi = AsyncMock()
    mi._get_user_data = AsyncMock(return_value={"userId": 1135463})

    async def _post(endpoint, json=None):
        parts = endpoint.split("/")
        metric, method = parts[-3], int(parts[-1])
        data = responses.get((metric, method))
        if data is None:
            return APIResponse(success=False, message="not found")
        return APIResponse(success=True, data=data)

    mi.post = AsyncMock(side_effect=_post)
    mock_client.return_value.__aenter__.return_value = mi
    return p, mi


@pytest.mark.asyncio
async def test_power_methods_fingerprinted_and_errors_skipped():
    resp = {
        # CTS: derives the threshold (225 != input 250) → derives_threshold True
        ("power", 2): {"zones": _zones(["Recovery Miles", "Power Intervals"]),
                       "lactateThreshold": 225},
        # Coggan: threshold echoed (250) → derives_threshold False
        ("power", 4): {"zones": _zones(["Zone 1 - Recovery/Walking",
                                        "Zone 7 - Anaerobic Capacity"]),
                       "lactateThreshold": 250},
        # method 9 absent → POST errors → skipped
    }
    p, _ = _client(resp)
    try:
        out = await tp_get_zone_methods(metric="power")
    finally:
        p.stop()
    methods = out["methods"]["power"]
    by = {m["method"]: m for m in methods}
    assert set(by) == {2, 4}                       # errored ints skipped
    assert by[2]["derives_threshold"] is True
    assert by[4]["derives_threshold"] is False
    assert by[2]["zone_count"] == 2
    assert "Power Intervals" in by[2]["labels"]
    # probe order preserved (2 before 4)
    assert [m["method"] for m in methods] == [2, 4]


@pytest.mark.asyncio
async def test_speed_uses_threshold_speed_field():
    resp = {("speed", 3): {"zones": _zones(["Z1", "Z2"]), "thresholdSpeed": 3.2}}
    p, _ = _client(resp)
    try:
        out = await tp_get_zone_methods(metric="speed")
    finally:
        p.stop()
    m = out["methods"]["speed"][0]
    assert m["method"] == 3
    assert m["derives_threshold"] is True           # 3.2 != input 4.0


@pytest.mark.asyncio
async def test_all_metrics_when_metric_omitted():
    resp = {
        ("power", 1): {"zones": _zones(["1"]), "lactateThreshold": 250},
        ("heartrate", 1): {"zones": _zones(["Z1"]), "lactateThreshold": 160},
        ("speed", 2): {"zones": _zones(["Z1"]), "thresholdSpeed": 4.0},
    }
    p, _ = _client(resp)
    try:
        out = await tp_get_zone_methods()
    finally:
        p.stop()
    assert set(out["methods"]) == {"power", "heartrate", "speed"}
    assert out["methods"]["power"][0]["method"] == 1


@pytest.mark.asyncio
async def test_invalid_metric_rejected():
    out = await tp_get_zone_methods(metric="cadence")
    assert out["isError"] and out["error_code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_missing_user_id_is_auth_error():
    p = patch("tp_mcp.tools.zone_methods.TPClient")
    mock_client = p.start()
    mi = AsyncMock()
    mi._get_user_data = AsyncMock(return_value={})
    mock_client.return_value.__aenter__.return_value = mi
    try:
        out = await tp_get_zone_methods(metric="power")
    finally:
        p.stop()
    assert out["isError"] and out["error_code"] == "AUTH_INVALID"
