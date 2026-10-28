"""Size regression for the opt-in compact output of tp_get_workouts / tp_get_metrics.

The fixtures are synthetic (generated, no real athlete data) but carry the
field set and typical text lengths of the v6 workouts list and the v3
consolidated-metrics endpoints: 28 days / 46 workouts and 14 days / ~12
metrics per day.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools.metrics import tp_get_metrics
from tp_mcp.tools.workouts import tp_get_workouts

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _size(payload) -> int:
    return len(json.dumps(payload, indent=2))


async def _call(module, fn, data, *args, **kwargs):
    with patch(f"tp_mcp.tools.{module}.TPClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
        mock_instance.get = AsyncMock(return_value=APIResponse(success=True, data=data))
        mock_client.return_value.__aenter__.return_value = mock_instance
        return await fn(*args, **kwargs)


class TestCompactSize:
    @pytest.mark.asyncio
    async def test_workouts_28d_compact_is_at_least_a_third_smaller(self):
        raw = json.loads((FIXTURES / "workouts_28d_v6.json").read_text())
        full = await _call("workouts", tp_get_workouts, raw, "2026-09-30", "2026-10-27")
        compact = await _call("workouts", tp_get_workouts, raw, "2026-09-30", "2026-10-27", compact=True)

        assert full["count"] == compact["count"] == 46
        assert all("description" not in w for w in compact["workouts"])
        assert any(w["has_structure"] for w in compact["workouts"])
        assert all(len(w["title"]) <= 80 for w in compact["workouts"])
        # Default output already omits structures, so the saving here is the
        # description text; measured 32.7 KB -> 20.9 KB (-36%) on this fixture.
        assert _size(compact) <= 0.67 * _size(full)

    @pytest.mark.asyncio
    async def test_metrics_14d_compact_is_at_least_80_percent_smaller(self):
        raw = json.loads((FIXTURES / "metrics_14d_v3.json").read_text())
        full = await _call("metrics", tp_get_metrics, raw, "2026-10-14", "2026-10-27")
        compact = await _call("metrics", tp_get_metrics, raw, "2026-10-14", "2026-10-27", compact=True)

        assert full["count"] == compact["count"] == 14
        assert all(set(row) >= {"date", "hrv", "pulse", "sleep_hours", "weight"} for row in compact["metrics"])
        # Measured 51.6 KB -> 5.4 KB (-89%) on this fixture.
        assert _size(compact) <= 0.2 * _size(full)
