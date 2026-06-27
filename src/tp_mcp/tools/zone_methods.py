"""Discover TrainingPeaks zone-calculation methods.

TP exposes no endpoint that lists zone-calculation methods, and athlete settings
carry only the opaque ``calculationMethod`` integer (``zoneCalculatorId`` is
null, no name). However, the zone calculator

    POST /trainingzones/v1/users/{userId}/{metric}/calculate/{method}

returns each zone with a ``label`` and echoes the ``calculationMethod``. The zone
count and labels are method-intrinsic (stable across athletes; only the band
boundaries depend on the input threshold), so probing the method-int range
fingerprints every available method without hardcoding any names.

This is read-only: the calculator only computes, it never saves.
"""

import logging
from typing import Any

from tp_mcp.client import TPClient

logger = logging.getLogger("tp-mcp")

METRICS = ("power", "heartrate", "speed")

# Representative threshold body per metric. The values are arbitrary — only the
# returned zone LABELS and COUNT are read (method-intrinsic); the boundaries
# (which depend on these numbers) are intentionally ignored here.
_PROBE_BODY: dict[str, dict[str, Any]] = {
    "power": {"LTPower": 250},
    "heartrate": {"LTHR": 160, "maxHR": 190, "restingHR": 50},
    "speed": {"speed": 4.0, "distance": 3000},
}
_PROBE_THRESHOLD = {"power": 250.0, "heartrate": 160.0, "speed": 4.0}

# Method ints to probe. Observed in the wild: power {1..7}, HR {1..5, 31},
# speed {2, 5, 14}. A generous range is probed; unknown ints simply error and
# are skipped, so this stays correct if TP adds methods.
_PROBE_METHODS = list(range(0, 16)) + [31]


async def _probe_metric(
    client: TPClient, user_id: int, metric: str
) -> list[dict[str, Any]]:
    """Probe every candidate method int for one metric; return the ones that
    resolve, each as {method, zone_count, labels, derives_threshold}."""
    body = _PROBE_BODY[metric]
    threshold = _PROBE_THRESHOLD[metric]
    found: list[dict[str, Any]] = []
    for method in _PROBE_METHODS:
        endpoint = f"/trainingzones/v1/users/{user_id}/{metric}/calculate/{method}"
        resp = await client.post(endpoint, json={**body, "zoneType": method})
        if resp.is_error or not isinstance(resp.data, dict):
            continue
        zones = resp.data.get("zones")
        if not isinstance(zones, list) or not zones:
            continue
        # A method whose returned threshold differs from the input derives it
        # from a (field-)test — a direct threshold can't be set for it.
        derived = resp.data.get("lactateThreshold")
        if derived is None:
            derived = resp.data.get("thresholdSpeed")
        derives = (
            isinstance(derived, (int, float))
            and threshold > 0
            and abs(float(derived) - threshold) / threshold > 0.02
        )
        found.append(
            {
                "method": method,
                "zone_count": len(zones),
                "labels": [z.get("label") for z in zones if isinstance(z, dict)],
                "derives_threshold": bool(derives),
            }
        )
    return found


async def tp_get_zone_methods(metric: str | None = None) -> dict[str, Any]:
    """List available zone-calculation methods, each with its zone count and
    zone labels (the method's fingerprint).

    Args:
        metric: ``power``, ``heartrate``, or ``speed``. Omit to probe all three.

    Returns:
        ``{"methods": {metric: [{method, zone_count, labels,
        derives_threshold}, ...]}}`` or an error envelope.
    """
    if metric is not None and metric not in METRICS:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": f"metric must be one of {METRICS} or omitted.",
        }
    metrics = (metric,) if metric else METRICS

    async with TPClient() as client:
        user_data = await client._get_user_data()
        user_id = (user_data or {}).get("userId")
        if not isinstance(user_id, int):
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get user id. Re-authenticate.",
            }
        methods = {m: await _probe_metric(client, user_id, m) for m in metrics}

    return {"methods": methods}
