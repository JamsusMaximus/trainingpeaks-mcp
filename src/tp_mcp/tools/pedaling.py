"""Pedaling metrics from the analysis time series (no FIT parsing needed).

The analysis charts endpoint already carries per-sample left/right balance,
torque effectiveness and pedal smoothness when a dual-sided power meter was
used. TrainingPeaks' channel averages include coasting samples (value 0), so
they understate e.g. pedal smoothness. This module recomputes the metrics over
pedaling samples only and adds what the averages cannot show:

- balance by power range (does one leg take over at higher watts?),
- balance per quarter of the ride (does it drift with fatigue?).

Balance is power-weighted: the share of total work delivered by the left leg,
not the mean of per-sample percentages.
"""

from statistics import median
from typing import Any

BALANCE = "LeftRightBalance"  # % left
POWER = "Power"
CADENCE = "Cadence"
SIDE_METRICS = {
    "torque_effectiveness_pct": ("LeftTorqueEffectiveness", "RightTorqueEffectiveness"),
    "pedal_smoothness_pct": ("LeftPedalSmoothness", "RightPedalSmoothness"),
}
POWER_BUCKET_W = 50
SEGMENTS = 4
MIN_SAMPLES = 30
COARSE_SPACING_S = 1.5


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _pedaling_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Samples with power, a real balance (strictly between 0 and 100) and, if present, cadence > 0."""
    out = []
    for row in rows:
        power, balance, cadence = _num(row.get(POWER)), _num(row.get(BALANCE)), _num(row.get(CADENCE))
        if power is None or power <= 0 or balance is None or not 0 < balance < 100:
            continue
        if cadence is not None and cadence <= 0:
            continue
        out.append(row)
    return out


def _left_share(rows: list[dict[str, Any]]) -> float | None:
    """Power-weighted left share in percent."""
    total = sum(float(r[POWER]) for r in rows)
    if total <= 0:
        return None
    return round(sum(float(r[POWER]) * float(r[BALANCE]) for r in rows) / total, 1)


def _mean(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [v for v in (_num(r.get(key)) for r in rows) if v is not None and v > 0]
    return round(sum(values) / len(values), 1) if values else None


def _spacing_s(rows: list[dict[str, Any]]) -> float:
    times = [t for t in (_num(r.get("time")) for r in rows) if t is not None]
    gaps = [b - a for a, b in zip(times, times[1:], strict=False) if b > a]
    return float(median(gaps)) if gaps else 1.0


def _by_power(rows: list[dict[str, Any]], spacing: float) -> list[dict[str, Any]]:
    buckets: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        buckets.setdefault(int(float(row[POWER]) // POWER_BUCKET_W) * POWER_BUCKET_W, []).append(row)
    return [
        {"range_w": [low, low + POWER_BUCKET_W], "left_pct": _left_share(group),
         "minutes": round(len(group) * spacing / 60, 1)}
        for low, group in sorted(buckets.items())
    ]


def _by_segment(rows: list[dict[str, Any]], spacing: float) -> list[dict[str, Any]]:
    size = -(-len(rows) // SEGMENTS)
    segments = []
    for index in range(SEGMENTS):
        group = rows[index * size:(index + 1) * size]
        if not group:
            continue
        segments.append({
            "segment": index + 1,
            "from_min": round(float(group[0].get("time") or 0) / 60, 1),
            "to_min": round(float(group[-1].get("time") or 0) / 60, 1),
            "left_pct": _left_share(group),
            "avg_power_w": round(sum(float(r[POWER]) for r in group) / len(group)),
        })
    return segments


def pedaling_summary(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pedaling block for tp_analyze_workout, or None without dual-sided data."""
    pedaling = _pedaling_rows(rows)
    if len(pedaling) < MIN_SAMPLES:
        return None
    spacing = _spacing_s(rows)
    summary: dict[str, Any] = {
        "left_pct": _left_share(pedaling),
        "basis": "power-weighted share of work from the left leg, pedaling samples only (power > 0)",
        "pedaling_minutes": round(len(pedaling) * spacing / 60, 1),
        "sample_spacing_s": round(spacing, 1),
    }
    for name, (left_key, right_key) in SIDE_METRICS.items():
        left, right = _mean(pedaling, left_key), _mean(pedaling, right_key)
        if left is not None or right is not None:
            summary[name] = {"left": left, "right": right}
    summary["by_power"] = _by_power(pedaling, spacing)
    summary["by_segment"] = _by_segment(pedaling, spacing)
    if spacing > COARSE_SPACING_S:
        summary["note"] = f"Time series is downsampled (~{spacing:.0f} s per point); values are approximate."
    return summary
