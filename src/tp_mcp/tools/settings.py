"""Athlete settings tools: zones, FTP, thresholds, nutrition."""

import copy
import logging
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from tp_mcp.client import TPClient
from tp_mcp.tools._validation import format_validation_error
from tp_mcp.tools.workouts import SPORT_TYPE_MAP

logger = logging.getLogger("tp-mcp")

POWER_ZONE_LABELS = [
    "Recovery",
    "Endurance",
    "Tempo",
    "Threshold",
    "VO2 Max",
    "Anaerobic Capacity",
]
POWER_ZONE_MAXIMUM = 2000

# Sport name (case-insensitive) -> zone workoutTypeId. Reuses the connector's
# authoritative SPORT_TYPE_MAP, so a new TP sport needs no change here. 'default'
# / 'general' target the Default (0) zone set (not a sport).
_ZONE_WTID: dict[str, int] = {"default": 0, "general": 0}
_ZONE_WTID.update({name.lower(): value_id for name, (_fam, value_id) in SPORT_TYPE_MAP.items()})


class FTPInput(BaseModel):
    """Validates FTP input."""

    ftp: int = Field(gt=0, le=2000)
    workout_type: str = Field(default="bike")

    @field_validator("workout_type")
    @classmethod
    def check_ftp_type(cls, v: str) -> str:
        if v.lower() not in _ZONE_WTID:
            raise ValueError(f"workout_type must be one of {sorted(_ZONE_WTID)}")
        return v


class HRZonesInput(BaseModel):
    """Validates HR zones input."""

    threshold_hr: int | None = Field(default=None, gt=50, le=250)
    max_hr: int | None = Field(default=None, gt=50, le=250)
    resting_hr: int | None = Field(default=None, gt=20, le=120)
    workout_type: str = Field(default="general")

    @field_validator("workout_type")
    @classmethod
    def check_type(cls, v: str) -> str:
        if v.lower() not in _ZONE_WTID:
            raise ValueError(f"workout_type must be one of {sorted(_ZONE_WTID)}")
        return v


class SpeedZonesInput(BaseModel):
    """Validates speed zones input."""

    run_threshold_pace: str | None = None
    swim_threshold_pace: str | None = None

    @field_validator("run_threshold_pace", "swim_threshold_pace")
    @classmethod
    def check_pace_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.match(r"^\d{1,2}:\d{2}(/\w+)?$", v):
            raise ValueError(f"Invalid pace format '{v}'. Use 'M:SS' (e.g. '4:30/km' or '1:45/100m')")
        return v


_PACE_UNIT_METRES = {"km": 1000.0, "mi": 1609.344, "mile": 1609.344,
                     "miles": 1609.344, "m": 1.0, "yd": 0.9144}


def _parse_pace_to_ms(pace_str: str, is_swim: bool = False) -> float:
    """Parse a pace string ('M:SS[/unit]') to metres per second, HONOURING the
    unit (km / mi / 100m / 100yd / …). Unknown units raise rather than being
    silently treated as km/100m. Default unit: 100m for swim, km otherwise.
    """
    time_part, _, unit_part = pace_str.partition("/")
    unit = unit_part.strip().lower() or ("100m" if is_swim else "km")
    mo = re.fullmatch(r"(\d*)\s*(km|miles?|mi|yd|m)", unit)
    if not mo:
        raise ValueError(f"Unknown pace unit '/{unit_part.strip()}' in '{pace_str}'")
    count = int(mo.group(1)) if mo.group(1) else 1
    metres = count * _PACE_UNIT_METRES[mo.group(2)]

    mm, _, ss = time_part.strip().partition(":")
    total_seconds = int(mm) * 60 + int(ss)
    if total_seconds == 0:
        raise ValueError(f"Invalid pace: {pace_str}")
    return metres / total_seconds


async def tp_get_athlete_settings() -> dict[str, Any]:
    """Get athlete settings including FTP, thresholds, zones, and profile.

    Returns:
        Dict with all athlete settings.
    """
    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v1/athletes/{athlete_id}/settings"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        if not response.data or not isinstance(response.data, dict):
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "No settings data returned.",
            }

        return {"settings": response.data}


# ── Zone-update helpers (method-agnostic, no hardcoded discovery results) ──────
# workoutTypeId is TP's STABLE type identifier (0 default / 1 swim / 2 bike /
# 3 run), used ONLY to locate the right zone group. The group's calculationMethod,
# Distance-Time `distance`, zoneCalculatorId, band structure — and any field TP
# adds in future — are read from the live payload and preserved verbatim; the
# connector never assumes a calculation method or bakes in probed values.


def _select_group_index(groups: list[Any], wtid: int) -> tuple[int, str | None]:
    """Index of the zone group whose workoutTypeId == wtid; fall back to the
    default (0) group, then the first. The note records any fallback."""
    for i, g in enumerate(groups):
        if isinstance(g, dict) and g.get("workoutTypeId") == wtid:
            return i, None
    for i, g in enumerate(groups):
        if isinstance(g, dict) and g.get("workoutTypeId") == 0:
            return i, f"no zone set for workoutTypeId={wtid}; updated the default (0) set"
    return 0, f"no zone set for workoutTypeId={wtid} or default; updated the first set"


def _rescaled_group(
    group: dict[str, Any],
    new_threshold: float | None,
    *,
    integer: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    """Deep-copy `group`, set `threshold` (None = keep) and scale every zone band
    by the new/old ratio. ALL other fields ride through untouched, so the
    athlete's method / Distance-Time `distance` / calculator id are never
    altered. TP does NOT recompute bands on save (verified live), so the
    connector does — proportionally to the threshold (correct for
    threshold-anchored methods); it never assumes a method formula.
    Returns (new_group, error)."""
    old = group.get("threshold")
    if not isinstance(old, (int, float)) or old <= 0:
        return None, "existing threshold is missing or zero"
    zones = group.get("zones") or []
    interior_maxima = [z.get("maximum") for z in zones[:-1] if isinstance(z, dict)]
    if any(not isinstance(m, (int, float)) for m in interior_maxima):
        return None, "existing zone bands are malformed"
    target = float(old) if new_threshold is None else float(new_threshold)
    ratio = target / float(old)
    new_group = copy.deepcopy(group)
    new_group["threshold"] = round(target) if integer else target
    zlist = new_group.get("zones") or []
    last = len(zlist) - 1
    for i, z in enumerate(zlist):
        if not isinstance(z, dict):
            continue
        for bound in ("minimum", "maximum"):
            # Keep the final zone's artificial ceiling (e.g. 2000 W) unscaled.
            if i == last and bound == "maximum":
                continue
            v = z.get(bound)
            if isinstance(v, (int, float)):
                z[bound] = round(v * ratio) if integer else v * ratio
    return new_group, None


_CALC_METRIC = {"powerzones": "power", "heartratezones": "heartrate",
               "speedzones": "speed"}


async def _get_user_id(client: "TPClient") -> int | None:
    """Authenticated (coach) user id for the zone-calculator URL — distinct from
    the targeted athlete; the calculator runs under the caller's user."""
    ud = await client._get_user_data()
    uid = (ud or {}).get("userId") or (ud or {}).get("personId")
    return uid if isinstance(uid, int) else None


async def _calculated_zones(
    client: "TPClient", metric: str, group: dict[str, Any],
    new_threshold: float | None, extra_fields: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]] | None, float | None]:
    """METHOD-CORRECT bands from TP's own zone calculator (the same call the web
    UI "Calculate" makes). Returns (mapped [{label,minimum,maximum}],
    derived_threshold) — the calculator ECHOES the threshold for threshold-anchored
    methods but DERIVES a different one for test-based methods (Distance-Time), so
    the caller stores the derived value and can detect the test-based case.
    Returns (None, None) on manual method / no calculator / bad response."""
    method = group.get("calculationMethod")
    if not isinstance(method, int):
        return None, None
    uid = await _get_user_id(client)
    if uid is None:
        return None, None
    extra = extra_fields or {}
    thr = group.get("threshold") if new_threshold is None else new_threshold
    body: dict[str, Any] = {"zoneType": method}
    if metric == "heartrate":
        body["LTHR"] = thr
        body["maxHR"] = extra.get("maximumHeartRate", group.get("maximumHeartRate"))
        body["restingHR"] = extra.get("restingHeartRate", group.get("restingHeartRate"))
    elif metric == "power":
        body["LTPower"] = thr
    elif metric == "speed":
        body["speed"] = thr
        if group.get("distance") is not None:
            body["distance"] = group.get("distance")
    else:
        return None, None
    resp = await client.post(
        f"/trainingzones/v1/users/{uid}/{metric}/calculate/{method}", json=body)
    if resp.is_error or not isinstance(resp.data, dict):
        return None, None
    raw = resp.data.get("zones")
    if not isinstance(raw, list) or not raw:
        return None, None
    use_double = metric == "speed"
    out: list[dict[str, Any]] = []
    for z in raw:
        if not isinstance(z, dict):
            return None, None
        mn = z.get("minimumAsDouble") if use_double else z.get("minimum")
        mx = z.get("maximumAsDouble") if use_double else z.get("maximum")
        # reject non-numeric / NaN (NaN != NaN) -> caller falls back
        if not isinstance(mn, (int, float)) or not isinstance(mx, (int, float)) or mn != mn or mx != mx:
            return None, None
        out.append({"label": z.get("label"), "minimum": mn, "maximum": mx})
    derived = resp.data.get("thresholdSpeed")
    if not isinstance(derived, (int, float)):
        derived = resp.data.get("lactateThreshold")
    return out, (derived if isinstance(derived, (int, float)) else None)


async def _put_zone_array(
    client: "TPClient", athlete_id: int, put_path: str, payload: list[Any],
) -> dict[str, Any] | None:
    """PUT the full zone-group array. Returns an error dict or None on success."""
    pr = await client.put(f"/fitness/v2/athletes/{athlete_id}/{put_path}", json=payload)
    if pr.is_error:
        return {"isError": True,
                "error_code": pr.error_code.value if pr.error_code else "API_ERROR",
                "message": pr.message}
    return None


async def _update_single_zone_set(
    client: "TPClient", athlete_id: int, settings_key: str, put_path: str,
    wtid: int, new_threshold: float | None, *, integer: bool,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """GET settings → locate the wtid group → rescale → PUT the full array (the
    only shape TP accepts). `extra_fields` sets extra anchors verbatim (HR
    maximumHeartRate/restingHeartRate)."""
    sr = await client.get(f"/fitness/v1/athletes/{athlete_id}/settings")
    if sr.is_error:
        return {"isError": True,
                "error_code": sr.error_code.value if sr.error_code else "API_ERROR",
                "message": sr.message}
    if not isinstance(sr.data, dict):
        return {"isError": True, "error_code": "API_ERROR", "message": "No settings data returned."}
    groups = sr.data.get(settings_key)
    if not isinstance(groups, list) or not groups:
        return {"isError": True, "error_code": "API_ERROR",
                "message": f"No {settings_key} found in athlete settings."}
    idx, note = _select_group_index(groups, wtid)
    metric = _CALC_METRIC.get(put_path, "")
    calc_zones, derived = await _calculated_zones(client, metric, groups[idx], new_threshold, extra_fields)
    method_correct = calc_zones is not None
    if method_correct:
        # Test-based methods (e.g. Distance/Time) DERIVE the threshold from the
        # input as a test result — they can't have a threshold set directly.
        if (new_threshold is not None and derived is not None
                and abs(derived - new_threshold) > 0.02 * max(abs(new_threshold), 1.0)):
            return {"isError": True, "error_code": "TEST_BASED_METHOD",
                    "message": "This zone set derives its threshold from a test "
                               "(e.g. Distance/Time); a threshold can't be set directly. "
                               "Change the calculation method or enter a test in TrainingPeaks."}
        new_group = copy.deepcopy(groups[idx])
        if new_threshold is not None:
            store = derived if derived is not None else new_threshold
            new_group["threshold"] = round(store) if integer else store
        if extra_fields:
            for k, v in extra_fields.items():
                if v is not None:
                    new_group[k] = v
        new_group["zones"] = calc_zones
    else:
        new_group, err = _rescaled_group(groups[idx], new_threshold, integer=integer)
        if err or new_group is None:
            return {"isError": True, "error_code": "ZONE_RESCALE", "message": err or "rescale failed"}
        if extra_fields:
            for k, v in extra_fields.items():
                if v is not None:
                    new_group[k] = v
    payload = list(groups)
    payload[idx] = new_group
    put_err = await _put_zone_array(client, athlete_id, put_path, payload)
    if put_err:
        return put_err
    notes = [note] if note else []
    if not method_correct:
        notes.append("zones rescaled proportionally (no server calculator for this method)")
        if new_threshold is None:
            notes.append("only anchors changed; bands unchanged — recompute in TP")
    result: dict[str, Any] = {
        "success": True,
        "workout_type_id": new_group.get("workoutTypeId"),
        "calculation_method": new_group.get("calculationMethod"),
        "method_correct": method_correct,
        "threshold": new_group.get("threshold"),
        "zones": new_group.get("zones"),
    }
    if notes:
        result["note"] = "; ".join(notes)
    return result


async def tp_update_ftp(ftp: int, workout_type: str = "bike") -> dict[str, Any]:
    """Update FTP (power threshold) and rescale the matching power-zone set.

    Args:
        ftp: Functional Threshold Power in watts.
        workout_type: which power set to update — 'bike' (default; FTP is a
            cycling concept), 'run' (running power) or 'default'. Falls back to
            the default set if the athlete has no sport-specific one.

    The set's calculation method and structure are preserved; bands are rescaled
    proportionally. A fresh athlete with no usable bands gets a Coggan model.
    """
    try:
        params = FTPInput(ftp=ftp, workout_type=workout_type)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {"isError": True, "error_code": "VALIDATION_ERROR", "message": msg}

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {"isError": True, "error_code": "AUTH_INVALID",
                    "message": "Could not get athlete ID. Re-authenticate."}
        wtid = _ZONE_WTID.get(params.workout_type.lower(), _ZONE_WTID["bike"])
        result = await _update_single_zone_set(
            client, athlete_id, "powerZones", "powerzones", wtid,
            float(params.ftp), integer=True)
        if result.get("error_code") == "ZONE_RESCALE":
            result = await _ftp_coggan_fallback(client, athlete_id, params.ftp, wtid)
        if result.get("success"):
            result["ftp"] = params.ftp
        return result


async def _ftp_coggan_fallback(
    client: "TPClient", athlete_id: int, ftp: int, wtid: int,
) -> dict[str, Any]:
    """Build a default Coggan power-zone set when there are no bands to rescale."""
    sr = await client.get(f"/fitness/v1/athletes/{athlete_id}/settings")
    if sr.is_error or not isinstance(sr.data, dict):
        return {"isError": True, "error_code": "API_ERROR", "message": "No settings data returned."}
    groups = sr.data.get("powerZones")
    if not isinstance(groups, list) or not groups:
        return {"isError": True, "error_code": "API_ERROR",
                "message": "No power zones found in athlete settings."}
    idx, note = _select_group_index(groups, wtid)
    target = copy.deepcopy(groups[idx])
    existing = target.get("zones") or []
    labels = [z.get("label") for z in existing if isinstance(z, dict) and z.get("label")]
    if len(labels) != len(POWER_ZONE_LABELS):
        labels = list(POWER_ZONE_LABELS)
    maxima = [round(ftp * r) for r in (0.56, 0.76, 0.91, 1.06, 1.21)]
    zones: list[dict[str, Any]] = []
    lo = 0
    for label, hi in zip(labels[:-1], maxima, strict=False):
        zones.append({"label": label, "minimum": lo, "maximum": hi})
        lo = hi + 1
    zones.append({"label": labels[-1], "minimum": lo, "maximum": POWER_ZONE_MAXIMUM})
    target["threshold"] = ftp
    target["zones"] = zones
    payload = list(groups)
    payload[idx] = target
    put_err = await _put_zone_array(client, athlete_id, "powerzones", payload)
    if put_err:
        return put_err
    res: dict[str, Any] = {
        "success": True, "ftp": ftp, "workout_type_id": target.get("workoutTypeId"),
        "calculation_method": target.get("calculationMethod"),
        "threshold": ftp, "zones": zones,
    }
    if note:
        res["note"] = note
    return res


async def tp_update_hr_zones(
    threshold_hr: int | None = None,
    max_hr: int | None = None,
    resting_hr: int | None = None,
    workout_type: str = "general",
) -> dict[str, Any]:
    """Update heart-rate zones for a specific sport, preserving the method.

    Args:
        threshold_hr: Threshold (LTHR). When given, bands rescale to it.
        max_hr: Maximum HR (stored as an anchor; bands not auto-rescaled by it).
        resting_hr: Resting HR (stored as an anchor).
        workout_type: 'general' (default set), 'bike', 'run' or 'swim'.
    """
    try:
        params = HRZonesInput(
            threshold_hr=threshold_hr, max_hr=max_hr,
            resting_hr=resting_hr, workout_type=workout_type)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {"isError": True, "error_code": "VALIDATION_ERROR", "message": msg}

    if params.threshold_hr is None and params.max_hr is None and params.resting_hr is None:
        return {"isError": True, "error_code": "VALIDATION_ERROR",
                "message": "At least one of threshold_hr, max_hr, or resting_hr must be provided."}

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {"isError": True, "error_code": "AUTH_INVALID",
                    "message": "Could not get athlete ID. Re-authenticate."}
        wtid = _ZONE_WTID.get(params.workout_type.lower(), 0)
        extra: dict[str, Any] = {}
        if params.max_hr is not None:
            extra["maximumHeartRate"] = params.max_hr
        if params.resting_hr is not None:
            extra["restingHeartRate"] = params.resting_hr
        new_thr = float(params.threshold_hr) if params.threshold_hr is not None else None
        return await _update_single_zone_set(
            client, athlete_id, "heartRateZones", "heartratezones", wtid,
            new_thr, integer=True, extra_fields=extra)


async def tp_update_speed_zones(
    run_threshold_pace: str | None = None,
    swim_threshold_pace: str | None = None,
) -> dict[str, Any]:
    """Update run/swim THRESHOLD pace, recomputing bands with TP's own zone
    calculator (method preserved). Pace honours its unit (km / mi / 100m / 100yd).

    LIMITATION: a set whose method DERIVES its threshold from a test result
    (Speed/Pace "Distance / Time") cannot have a threshold set directly — the
    input would be treated as a test, deriving a different value. Such sets
    return ``TEST_BASED_METHOD`` (nothing written); configure them via a test in
    the TrainingPeaks UI. Threshold-anchored methods (Threshold Pace) update
    exactly.

    Args:
        run_threshold_pace: e.g. '4:30/km'.
        swim_threshold_pace: e.g. '1:45/100m'.
    """
    try:
        params = SpeedZonesInput(
            run_threshold_pace=run_threshold_pace,
            swim_threshold_pace=swim_threshold_pace)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {"isError": True, "error_code": "VALIDATION_ERROR", "message": msg}

    if params.run_threshold_pace is None and params.swim_threshold_pace is None:
        return {"isError": True, "error_code": "VALIDATION_ERROR",
                "message": "At least one of run_threshold_pace or swim_threshold_pace must be provided."}

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {"isError": True, "error_code": "AUTH_INVALID",
                    "message": "Could not get athlete ID. Re-authenticate."}
        sr = await client.get(f"/fitness/v1/athletes/{athlete_id}/settings")
        if sr.is_error:
            return {"isError": True,
                    "error_code": sr.error_code.value if sr.error_code else "API_ERROR",
                    "message": sr.message}
        if not isinstance(sr.data, dict):
            return {"isError": True, "error_code": "API_ERROR", "message": "No settings data returned."}
        groups = sr.data.get("speedZones")
        if not isinstance(groups, list) or not groups:
            return {"isError": True, "error_code": "API_ERROR",
                    "message": "No speed zones found in athlete settings."}

        working = list(groups)
        updated: list[dict[str, Any]] = []
        notes: list[str] = []
        plan = [("run", params.run_threshold_pace, False, 3),
                ("swim", params.swim_threshold_pace, True, 1)]
        for sport, pace, is_swim, wtid in plan:
            if pace is None:
                continue
            try:
                speed_ms = _parse_pace_to_ms(pace, is_swim=is_swim)
            except ValueError as e:
                return {"isError": True, "error_code": "VALIDATION_ERROR", "message": str(e)}
            idx, note = _select_group_index(working, wtid)
            calc_zones, derived = await _calculated_zones(client, "speed", working[idx], speed_ms, None)
            method_correct = calc_zones is not None
            if method_correct:
                if derived is not None and abs(derived - speed_ms) > 0.02 * max(abs(speed_ms), 1.0):
                    return {"isError": True, "error_code": "TEST_BASED_METHOD",
                            "message": f"{sport}: zone set derives its threshold from a test "
                                       "(e.g. Distance/Time); set it via a test in TrainingPeaks "
                                       "or change the method."}
                new_group = copy.deepcopy(working[idx])
                new_group["threshold"] = derived if derived is not None else speed_ms
                new_group["zones"] = calc_zones
            else:
                new_group, err = _rescaled_group(working[idx], speed_ms, integer=False)
                if err or new_group is None:
                    return {"isError": True, "error_code": "API_ERROR",
                            "message": f"{sport}: {err or 'rescale failed'}"}
            working[idx] = new_group
            if note:
                notes.append(f"{sport}: {note}")
            if not method_correct:
                notes.append(f"{sport}: zones rescaled proportionally (no server calculator)")
            updated.append({
                "sport": sport,
                "workout_type_id": new_group.get("workoutTypeId"),
                "calculation_method": new_group.get("calculationMethod"),
                "method_correct": method_correct,
                "distance": new_group.get("distance"),
                "threshold_ms": speed_ms,
                "zones": new_group.get("zones"),
            })

        put_err = await _put_zone_array(client, athlete_id, "speedzones", working)
        if put_err:
            return put_err
        result: dict[str, Any] = {"success": True, "updated": updated}
        if notes:
            result["note"] = "; ".join(notes)
        return result


# metric -> (settings array key, PUT path)
_METRIC_KEYS = {
    "power": ("powerZones", "powerzones"),
    "heartrate": ("heartRateZones", "heartratezones"),
    "speed": ("speedZones", "speedzones"),
}


async def tp_create_zones(
    metric: str,
    workout_type: str,
    calculation_method: int,
    threshold: float | None = None,
    pace: str | None = None,
    max_hr: int | None = None,
    resting_hr: int | None = None,
    distance: int = 0,
) -> dict[str, Any]:
    """Create a NEW per-sport zone set for an athlete that has none for that
    sport (use tp_update_ftp/hr_zones/speed_zones to change an EXISTING set).
    Bands are computed by TrainingPeaks' own calculator for the chosen method.

    Args:
        metric: 'power' | 'heartrate' | 'speed'.
        workout_type: sport for the set (e.g. 'bike', 'run', 'swim', 'xcski').
        calculation_method: the method int (see tp_get_zone_methods).
        threshold: FTP watts (power) or LTHR bpm (heartrate).
        pace: threshold pace (speed), e.g. '4:30/km' or '1:45/100m'.
        max_hr, resting_hr: optional anchors for heartrate methods.
        distance: optional, for speed sets.

    Limitation: test-based methods (Distance/Time) DERIVE the threshold from a
    test and can't be created from a plain threshold — return TEST_BASED_METHOD;
    set those up via a test in the TrainingPeaks UI.
    """
    metric = (metric or "").lower()
    if metric not in _METRIC_KEYS:
        return {"isError": True, "error_code": "VALIDATION_ERROR",
                "message": f"metric must be one of {sorted(_METRIC_KEYS)}."}
    wt = (workout_type or "").lower()
    if wt not in _ZONE_WTID:
        return {"isError": True, "error_code": "VALIDATION_ERROR",
                "message": f"workout_type must be one of {sorted(_ZONE_WTID)}."}
    if not isinstance(calculation_method, int) or isinstance(calculation_method, bool):
        return {"isError": True, "error_code": "VALIDATION_ERROR",
                "message": "calculation_method must be an integer (see tp_get_zone_methods)."}

    # Resolve the threshold value in the calculator's native units.
    if metric == "speed":
        if not pace:
            return {"isError": True, "error_code": "VALIDATION_ERROR",
                    "message": "pace is required for speed zones (e.g. '4:30/km')."}
        try:
            thr_value: float = _parse_pace_to_ms(pace, is_swim=(wt == "swim"))
        except ValueError as e:
            return {"isError": True, "error_code": "VALIDATION_ERROR", "message": str(e)}
    else:
        if threshold is None or float(threshold) <= 0:
            return {"isError": True, "error_code": "VALIDATION_ERROR",
                    "message": "threshold (watts for power, bpm for heartrate) is required."}
        thr_value = float(threshold)

    settings_key, put_path = _METRIC_KEYS[metric]
    wtid = _ZONE_WTID[wt]
    integer = metric != "speed"

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {"isError": True, "error_code": "AUTH_INVALID",
                    "message": "Could not get athlete ID. Re-authenticate."}
        sr = await client.get(f"/fitness/v1/athletes/{athlete_id}/settings")
        if sr.is_error:
            return {"isError": True,
                    "error_code": sr.error_code.value if sr.error_code else "API_ERROR",
                    "message": sr.message}
        if not isinstance(sr.data, dict):
            return {"isError": True, "error_code": "API_ERROR", "message": "No settings data returned."}
        groups = sr.data.get(settings_key)
        groups = list(groups) if isinstance(groups, list) else []
        if any(isinstance(g, dict) and g.get("workoutTypeId") == wtid for g in groups):
            return {"isError": True, "error_code": "ZONES_EXIST",
                    "message": f"{metric} zones already exist for workout_type '{wt}' "
                               "(workoutTypeId={}); use the update tool to change the "
                               "threshold.".format(wtid)}

        # Synthetic group carrying the chosen method/anchors → calculator.
        seed: dict[str, Any] = {"calculationMethod": calculation_method, "threshold": thr_value}
        extra: dict[str, Any] = {}
        if metric == "heartrate":
            extra = {"maximumHeartRate": max_hr, "restingHeartRate": resting_hr}
        elif metric == "speed":
            seed["distance"] = distance or 0
        calc_zones, derived = await _calculated_zones(client, metric, seed, None, extra)
        if calc_zones is None:
            return {"isError": True, "error_code": "API_ERROR",
                    "message": f"Calculator returned no zones for method {calculation_method} "
                               f"({metric}); check the method int (see tp_get_zone_methods)."}
        if derived is not None and abs(derived - thr_value) > 0.02 * max(abs(thr_value), 1.0):
            return {"isError": True, "error_code": "TEST_BASED_METHOD",
                    "message": "This method derives its threshold from a test "
                               "(e.g. Distance/Time); create it via a test in the "
                               "TrainingPeaks UI, or pick a threshold-anchored method."}

        new_group: dict[str, Any] = {
            "zoneCalculatorId": None,
            "threshold": round(thr_value) if integer else thr_value,
            "calculationMethod": calculation_method,
            "workoutTypeId": wtid,
            "zones": calc_zones,
        }
        if metric == "heartrate":
            new_group["maximumHeartRate"] = max_hr
            new_group["restingHeartRate"] = resting_hr
        elif metric == "speed":
            new_group["distance"] = distance or 0

        put_err = await _put_zone_array(client, athlete_id, put_path, groups + [new_group])
        if put_err:
            return put_err
        return {
            "success": True,
            "created": True,
            "metric": metric,
            "workout_type": wt,
            "workout_type_id": wtid,
            "calculation_method": calculation_method,
            "threshold": new_group["threshold"],
            "zones": calc_zones,
        }


async def tp_update_nutrition(planned_calories: int) -> dict[str, Any]:
    """Update nutrition settings.

    Args:
        planned_calories: Planned daily calories.

    Returns:
        Dict with confirmation or error.
    """
    if planned_calories < 0 or planned_calories > 20000:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "planned_calories must be between 0 and 20000.",
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v1/athletes/{athlete_id}/nutritionsettings"
        payload = {"plannedCalories": planned_calories}
        response = await client.post(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {
            "success": True,
            "planned_calories": planned_calories,
        }


async def tp_get_pool_length_settings() -> dict[str, Any]:
    """Get pool length settings.

    Returns:
        Dict with pool length options and default.
    """
    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v1/athletes/{athlete_id}/poollengthsettings"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {"pool_length_settings": response.data}
