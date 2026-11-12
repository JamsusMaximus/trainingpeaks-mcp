"""Heat metrics from a CORE body-temperature sensor in the analysis time series.

The charts endpoint carries per-sample CoreTemperature, SkinTemperature and
HeatStrainIndex (HSI, 0-10) when a CORE sensor was worn. This module turns them
into what heat-training conversations need:

- CORE's Heat Zones on the HSI scale (Zone 1 0.0-0.9, Zone 2 1.0-2.9,
  Zone 3 3.0-6.9 = heat training zone, Zone 4 7+ = to avoid), minutes per zone
  and time until Zone 3 was first reached,
- core temperature start/avg/max/end and rise, minutes at or above 38.0/38.5/39.0 C
  (for athletes who work with temperature-based zones from a heat ramp test),
- skin temperature and the core-skin gradient (a smaller gradient means the
  body sheds heat less easily),
- per quarter of the session: core, HSI, heart rate and power or speed, to see
  drift at a given load.

CORE's Heat Adaptation Score uses an unpublished formula and is not computed.
For the Heat Training Load (HTL, 0-10) CORE publishes a table of HTL by time
held at a given HSI; `heat_training_load_estimate` reads a session against that
table (see HTL_TABLE). The app additionally uses heart rate, so its value can
differ — the estimate is labelled as such.
"""

from statistics import median
from typing import Any

CORE = "CoreTemperature"
SKIN = "SkinTemperature"
HSI = "HeatStrainIndex"
AMBIENT = "Temperature"
QUALITY = "CoreDataQuality"
HR = "HeartRate"
POWER = "Power"
SPEED = "Speed"  # km/h (charts metadata unit "kph", checked on real runs and rides)

# CORE Heat Zones by Heat Strain Index (upper bounds exclusive, last open)
HSI_ZONES = ((1, 0.0, 1.0), (2, 1.0, 3.0), (3, 3.0, 7.0), (4, 7.0, None))
# CORE "Heat Training Load" article: HTL by duration held at a final HSI
# (assumes 20-40 min to reach it). Column HSI -> [(minutes, HTL), ...].
HTL_TABLE: dict[float, list[tuple[int, float]]] = {
    1.5: [(30, 0.6), (45, 0.9), (60, 1.1), (90, 1.3), (120, 1.4), (180, 1.4)],
    2.5: [(30, 1.4), (45, 2.0), (60, 2.6), (90, 3.8), (120, 4.9), (180, 7.3)],
    3.5: [(30, 4.0), (45, 5.6), (60, 7.3), (90, 10.0)],
    4.5: [(30, 5.1), (45, 7.0), (60, 8.8), (90, 10.0)],
    5.5: [(30, 5.9), (45, 7.9), (60, 9.8), (90, 10.0)],
    6.5: [(30, 6.3), (45, 8.3), (60, 10.0)],
}
HTL_MAX = 10.0
CORE_GUIDANCE = (
    "CORE guidance: Zone 1 no heat training; Zone 2 partial adaptation (slower, not the full "
    "potential); Zone 3 optimal - reach it within 20-40 min, then hold it continuously for 30-80 min "
    "(45-60 typical); Zone 4 harmful, reduce intensity. Safety: keep core below 39 C, HSI below 7 "
    "and Zone 3 at most 100 min. Thresholds are individual (some athletes need HSI 5-6). Full "
    "adaptation: 10-14 sessions with 45-80 min in Zone 3 within 2-12 weeks; daily or every other "
    "day is fastest, 2-3 per week slower. Maintenance: 1-3 sessions per week. Adaptations decay "
    "about 2.5 % per day without heat training and are gone after 5-6 weeks. Heat Adaptation Score "
    "guide: HTL 9-10 on 5-6 days/week -> 85-95 % within about 2 weeks; HTL 5-6 less often -> about "
    "84 % over 12 weeks; maintained with 1-2 sessions/week."
)
SAFE_CORE_C = 39.0
SAFE_HSI = 7.0
SAFE_ZONE3_MIN = 100
CORE_THRESHOLDS_C = (38.0, 38.5, 39.0)
CORE_RANGE_C = (35.0, 42.5)  # outside: sensor artefact, not a body temperature
EDGE_S = 300  # start/end values: median of the first/last 5 minutes
SEGMENTS = 4
MIN_SAMPLES = 30
COARSE_SPACING_S = 1.5


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _core_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        core = _num(row.get(CORE))
        if core is not None and CORE_RANGE_C[0] <= core <= CORE_RANGE_C[1]:
            out.append(row)
    return out


def _spacing_s(rows: list[dict[str, Any]]) -> float:
    times = [t for t in (_num(r.get("time")) for r in rows) if t is not None]
    gaps = [b - a for a, b in zip(times, times[1:], strict=False) if b > a]
    return float(median(gaps)) if gaps else 1.0


def _avg(rows: list[dict[str, Any]], key: str, digits: int = 1) -> float | None:
    values = [v for v in (_num(r.get(key)) for r in rows) if v is not None]
    return round(sum(values) / len(values), digits) if values else None


def _max(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [v for v in (_num(r.get(key)) for r in rows) if v is not None]
    return round(max(values), 1) if values else None


def _edge(rows: list[dict[str, Any]], key: str, spacing: float, last: bool) -> float | None:
    count = max(1, int(EDGE_S / spacing))
    part = rows[-count:] if last else rows[:count]
    values = [v for v in (_num(r.get(key)) for r in part) if v is not None]
    return round(median(values), 2) if values else None


def _core_block(rows: list[dict[str, Any]], spacing: float) -> dict[str, Any]:
    start, end = _edge(rows, CORE, spacing, last=False), _edge(rows, CORE, spacing, last=True)
    peak = _max(rows, CORE)
    return {
        "start": start, "avg": _avg(rows, CORE, 2), "max": peak, "end": end,
        "rise": round(peak - start, 2) if peak is not None and start is not None else None,
        "minutes_at_or_above": {
            f"{t:.1f}": round(sum(1 for r in rows if float(r[CORE]) >= t) * spacing / 60, 1)
            for t in CORE_THRESHOLDS_C
        },
    }


def _hsi_zone(value: float) -> int:
    for zone, low, high in HSI_ZONES:
        if value >= low and (high is None or value < high):
            return zone
    return 1


def _hsi_block(rows: list[dict[str, Any]], spacing: float) -> dict[str, Any] | None:
    timed = [(_num(r.get("time")), _num(r.get(HSI))) for r in rows]
    values = [(t, h) for t, h in timed if h is not None and 0 <= h <= 10]
    if not values:
        return None
    minutes = {f"zone{z}": 0.0 for z, _, _ in HSI_ZONES}
    for _, h in values:
        minutes[f"zone{_hsi_zone(h)}"] += spacing / 60
    first_zone3 = next((t for t, h in values if h >= 3.0 and t is not None), None)
    start_t = values[0][0] or 0.0
    estimate = htl_estimate([h for _, h in values], spacing)
    return {
        "heat_training_load_estimate": estimate,
        "htl_basis": "estimate for this workout from CORE's published HTL table (time held per "
                     "HSI level); matched the CORE app within 0.3 on 14 of 19 single-workout days",
        "avg": round(sum(h for _, h in values) / len(values), 1),
        "max": round(max(h for _, h in values), 1),
        "minutes_in_zone": {k: round(v, 1) for k, v in minutes.items()},
        "minutes_to_zone3": round((first_zone3 - start_t) / 60, 1) if first_zone3 is not None else None,
        "zones": "CORE Heat Zones by HSI: 1 = 0-0.9, 2 = 1-2.9, 3 = 3-6.9 (heat training zone), 4 = 7+ (avoid)",
        "guidance": CORE_GUIDANCE,
    }


def _table_value(points: list[tuple[int, float]], minutes: float) -> float:
    """HTL for a duration from one table column: linear from 0 below 30 min, held after the last point."""
    if minutes <= 0:
        return 0.0
    first_min, first_htl = points[0]
    if minutes <= first_min:
        return first_htl * minutes / first_min
    for (m0, h0), (m1, h1) in zip(points, points[1:], strict=False):
        if minutes <= m1:
            return h0 + (h1 - h0) * (minutes - m0) / (m1 - m0)
    return points[-1][1]


def htl_estimate(hsi_values: list[float], spacing_s: float) -> float:
    """Estimated Heat Training Load (0-10) of one session from its HSI samples.

    For each table column (HSI 1.5 ... 6.5) the minutes at or above the column's
    band (column - 0.5) are read against that column; the highest value wins.
    Zone 1 (HSI < 1) never contributes.
    """
    best = 0.0
    for column, points in HTL_TABLE.items():
        minutes = sum(1 for h in hsi_values if h >= column - 0.5) * spacing_s / 60
        best = max(best, _table_value(points, minutes))
    return round(min(best, HTL_MAX), 1)


def _skin_block(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    pairs = [(_num(r.get(CORE)), _num(r.get(SKIN))) for r in rows]
    gradients = [c - s for c, s in pairs if c is not None and s is not None and 20 <= s <= 42]
    if not gradients:
        return None
    return {"avg": _avg(rows, SKIN), "max": _max(rows, SKIN),
            "core_skin_gradient_avg": round(sum(gradients) / len(gradients), 2)}


def _segments(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    size = -(-len(rows) // SEGMENTS)
    out = []
    for index in range(SEGMENTS):
        group = rows[index * size:(index + 1) * size]
        if not group:
            continue
        segment = {
            "segment": index + 1,
            "from_min": round(float(group[0].get("time") or 0) / 60, 1),
            "to_min": round(float(group[-1].get("time") or 0) / 60, 1),
            "core_avg": _avg(group, CORE, 2), "hsi_avg": _avg(group, HSI),
            "hr_avg": _avg(group, HR, 0), "power_avg_w": _avg(group, POWER, 0),
            "speed_avg_kmh": _avg(group, SPEED),
        }
        out.append({k: v for k, v in segment.items() if v is not None})
    return out


def _safety_warnings(summary: dict[str, Any]) -> list[str]:
    """CORE's safety limits: core below 39 C, HSI below 7, Zone 3 at most 100 min."""
    warnings = []
    core_minutes = summary["core_temp_c"]["minutes_at_or_above"].get(f"{SAFE_CORE_C:.1f}", 0.0)
    if core_minutes > 0:
        warnings.append(f"core at or above {SAFE_CORE_C:.0f} C for {core_minutes} min")
    zones = (summary.get("heat_strain_index") or {}).get("minutes_in_zone") or {}
    if zones.get("zone4", 0.0) > 0:
        warnings.append(f"HSI {SAFE_HSI:.0f}+ (Zone 4) for {zones['zone4']} min")
    if zones.get("zone3", 0.0) > SAFE_ZONE3_MIN:
        warnings.append(f"Zone 3 for {zones['zone3']} min, above CORE's {SAFE_ZONE3_MIN} min maximum")
    return warnings


def heat_summary(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Heat block for tp_analyze_workout, or None without CORE sensor data."""
    core = _core_rows(rows)
    if len(core) < MIN_SAMPLES:
        return None
    spacing = _spacing_s(rows)
    summary: dict[str, Any] = {
        "core_temp_c": _core_block(core, spacing),
        "minutes_with_core_data": round(len(core) * spacing / 60, 1),
        "sample_spacing_s": round(spacing, 1),
    }
    hsi = _hsi_block(core, spacing)
    skin = _skin_block(core)
    if skin:
        summary["skin_temp_c"] = skin
    if hsi and not skin:
        # HSI is computed from core AND skin temperature. Some recordings (e.g. indoor
        # apps) carry core and HSI but no skin channel; their HSI stays near 0 even
        # at a core of 38.5+ C. Zones and HTL would then wrongly say "no heat training".
        hsi = {"avg": hsi["avg"], "max": hsi["max"], "reliable": False,
               "note": "No skin temperature in this recording, so the Heat Strain Index is not usable "
                       "(zones and Heat Training Load omitted). Judge the session by core temperature "
                       "(minutes_at_or_above) or by the CORE app."}
    if hsi:
        summary["heat_strain_index"] = hsi
    ambient = _avg(rows, AMBIENT)
    if ambient is not None:
        summary["ambient_temp_c"] = {"avg": ambient, "max": _max(rows, AMBIENT)}
    quality = [q for q in (_num(r.get(QUALITY)) for r in core) if q is not None]
    if quality:
        summary["core_data_quality"] = {"min": min(quality), "share_at_max_pct": round(
            100 * sum(1 for q in quality if q == max(quality)) / len(quality), 1)}
    summary["by_segment"] = _segments(core)
    warnings = _safety_warnings(summary)
    if warnings:
        summary["safety_warnings"] = warnings
    if spacing > COARSE_SPACING_S:
        summary["note"] = f"Time series is downsampled (~{spacing:.0f} s per point); minutes are approximate."
    return summary
