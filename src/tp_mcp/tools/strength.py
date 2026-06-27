"""Structured strength / gym workouts via the Peaksware strength API.

Endurance workouts (`tp_create_workout`) use the main TrainingPeaks fitness API
with power/HR/pace interval structures. Strength workouts are a completely
different model — `workoutType: "StructuredStrength"` posted to the Peaksware
strength API (`api.peakswaresb.com`, same Bearer token we already use for
`tp_analyze_workout`). Exercises come from a fixed library (numeric string IDs);
the catalogue is baked into `tp_mcp/data/exercises.json` (no search endpoint
exists server-side), so `tp_search_exercises` runs fully offline.

Verified against the live API:
  • create  → POST   /rx/activity/v1/workouts/save        (returns numeric id)
  • summary → GET    /rx/activity/v1/workouts/{id}/summary
  • delete  → DELETE /rx/activity/v1/workouts/{id}
  • a prescription must declare its own `parameters` (the prescribed columns),
    distinct from the exercise's library parameters and each set's values;
  • parameter metadata may be minimal (`{parameter, inputFormat}`);
  • Superset/Circuit blocks require an equal number of sets across exercises.

This tool is intentionally unit-agnostic: it passes through whatever weight
parameter the caller supplies (`WeightKg`, `WeightLb`, `WeightPercentage`, …).
Choosing a default unit (e.g. kg) is the caller's concern, not the connector's.
"""

import json
import logging
import uuid
from functools import lru_cache
from typing import Any

import httpx

from tp_mcp.client import TPClient

logger = logging.getLogger("tp-mcp")

STRENGTH_API_BASE = "https://api.peakswaresb.com"
STRENGTH_TIMEOUT = 30.0

# The full parameter catalogue (per exercise sets). Integer-format ones are
# whole counts; everything else is decimal. Anything outside this set is
# rejected so a typo can't silently produce an empty column.
_INTEGER_PARAMS = {"Reps", "RepsPerSide", "Cals"}
_KNOWN_PARAMS = _INTEGER_PARAMS | {
    "WeightKg", "WeightLb", "WeightPerSideKg", "WeightPerSideLb", "WeightPercentage",
    "Duration", "DistanceMeters", "DistanceKm", "DistanceFt", "DistanceYd",
    "DistanceMiles", "HeightCm", "HeightM", "HeightIn", "HeightFt",
    "RPE", "Watts", "VelocityMetersPerSec",
}
_BLOCK_TYPES = {"WarmUp", "SingleExercise", "Superset", "Circuit", "CoolDown"}
# Blocks where every exercise must share the same number of sets (verified
# server constraint — otherwise save returns 400).
_EQUAL_SET_BLOCKS = {"Superset", "Circuit"}


def _input_format(parameter: str) -> str:
    return "Integer" if parameter in _INTEGER_PARAMS else "Decimal"


def _err(code: str, message: str) -> dict[str, Any]:
    return {"isError": True, "error_code": code, "message": message}


# ── Exercise catalogue (baked, offline) ─────────────────────────────────────
#
# PROVENANCE of `tp_mcp/data/exercises.json` (944 exercises):
#   The Peaksware strength API exposes NO list/search endpoint for the exercise
#   library, but each exercise IS readable individually by its numeric id (same
#   `api.peakswaresb.com` host + Bearer token as the workout endpoints). This
#   file is a one-time static snapshot built by fetching the exercises by id and
#   projecting each to the fields the tools use (id, title, videoUrl,
#   primary/secondary MuscleGroups, parameters). TP's library changes rarely;
#   the snapshot is refreshable by re-fetching by id if it ever drifts. It is
#   data, not code — reviewers can skip its contents.


@lru_cache(maxsize=1)
def _catalogue() -> dict[str, dict[str, Any]]:
    """The built-in exercise library, keyed by string id.

    Static snapshot baked from the per-id Peaksware endpoint — see the
    PROVENANCE note above for how it was generated / how to refresh it."""
    try:
        from importlib.resources import files

        text = files("tp_mcp").joinpath("data/exercises.json").read_text(encoding="utf-8")
    except Exception:  # dev / editable install fallback
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent / "data" / "exercises.json"
        text = path.read_text(encoding="utf-8")
    return json.loads(text)


async def tp_search_exercises(
    query: str,
    limit: int = 20,
    muscle_group: str | None = None,
) -> dict[str, Any]:
    """Search the built-in exercise library by name (offline, no API call).

    Args:
        query: Substring to match against exercise titles (case-insensitive).
            Empty query with a muscle_group returns exercises for that muscle.
        limit: Max results (1-100).
        muscle_group: Optional filter on primary/secondary muscle group
            (case-insensitive substring, e.g. "glute", "ham").

    Returns:
        Dict with `count` and `exercises` (id, title, video_url, muscle_groups,
        and the parameter names the exercise natively prescribes).
    """
    q = (query or "").strip().lower()
    mg = (muscle_group or "").strip().lower()
    limit = max(1, min(int(limit or 20), 100))
    if not q and not mg:
        return _err("VALIDATION_ERROR", "Provide a search query or a muscle_group.")

    out: list[dict[str, Any]] = []
    for ex in _catalogue().values():
        if q and q not in ex["title"].lower():
            continue
        if mg:
            groups = " ".join(
                ex.get("primaryMuscleGroups", []) + ex.get("secondaryMuscleGroups", [])
            ).lower()
            if mg not in groups:
                continue
        out.append(
            {
                "id": ex["id"],
                "title": ex["title"],
                "video_url": ex.get("videoUrl"),
                "muscle_groups": ex.get("primaryMuscleGroups", []),
                "parameters": [p["parameter"] for p in ex.get("parameters", [])],
            }
        )
    # Rank exact / prefix matches first for a name query — BEFORE truncating, so
    # an exact match that sits past `limit` in catalogue order isn't dropped.
    if q:
        out.sort(key=lambda e: (e["title"].lower() != q, not e["title"].lower().startswith(q)))
    out = out[:limit]
    return {"count": len(out), "exercises": out}


# ── Payload construction ────────────────────────────────────────────────────


def _validate_blocks(blocks: list[dict[str, Any]]) -> str | None:
    """Return an error string if the blocks are invalid, else None."""
    if not blocks:
        return "At least one block with one exercise is required."
    catalogue = _catalogue()
    for bi, block in enumerate(blocks):
        btype = block.get("type", "SingleExercise")
        if btype not in _BLOCK_TYPES:
            return f"block[{bi}].type {btype!r} is invalid. Allowed: {sorted(_BLOCK_TYPES)}."
        exercises = block.get("exercises") or []
        if not exercises:
            return f"block[{bi}] ({btype}) has no exercises."
        set_counts = []
        for ei, ex in enumerate(exercises):
            eid = str(ex.get("id", "")).strip()
            if eid not in catalogue:
                return f"block[{bi}].exercise[{ei}] id {eid!r} not in the exercise library."
            sets = ex.get("sets") or []
            if not sets:
                return f"block[{bi}].exercise[{ei}] ({catalogue[eid]['title']}) has no sets."
            set_counts.append(len(sets))
            for si, s in enumerate(sets):
                if not isinstance(s, dict) or not s:
                    return f"block[{bi}].exercise[{ei}].set[{si}] must be a non-empty map of parameter→value."
                bad = [p for p in s if p not in _KNOWN_PARAMS]
                if bad:
                    return (
                        f"block[{bi}].exercise[{ei}].set[{si}] has unknown parameter(s) {bad}. "
                        f"Allowed: {sorted(_KNOWN_PARAMS)}."
                    )
        if btype in _EQUAL_SET_BLOCKS and len(set(set_counts)) > 1:
            return (
                f"block[{bi}] ({btype}) requires the same number of sets for every "
                f"exercise (got {set_counts})."
            )
    return None


def _u() -> str:
    return str(uuid.uuid4())


def _build_prescription(ex: dict[str, Any], catalogue: dict[str, Any]) -> dict[str, Any]:
    eid = str(ex["id"])
    meta = catalogue[eid]
    sets_in = ex.get("sets") or []
    # Prescribed columns = union of parameters used across this exercise's sets,
    # in first-seen order.
    columns: list[str] = []
    for s in sets_in:
        for p in s:
            if p not in columns:
                columns.append(p)
    sets_out = []
    for s in sets_in:
        values = [
            {
                "id": _u(),
                "parameter": p,
                "prescribedValue": str(v),
                "executedValue": None,
                "inputFormat": _input_format(p),
            }
            for p, v in s.items()
        ]
        sets_out.append({"id": _u(), "parameterValues": values})
    return {
        "id": _u(),
        # Send only id + title; the server enriches the exercise's parameter
        # metadata from its own library. (Our baked catalogue flattens `unit`
        # to a string for search, which the save API rejects.)
        "exercise": {"id": eid, "title": meta["title"], "parameters": []},
        "parameters": [{"parameter": p, "inputFormat": _input_format(p)} for p in columns],
        "sets": sets_out,
        "coachNotes": ex.get("notes"),
        "setSummaryTemplate": None,
    }


def _build_payload(
    athlete_id: int,
    date: str,
    title: str,
    blocks: list[dict[str, Any]],
    instructions: str | None,
) -> dict[str, Any]:
    catalogue = _catalogue()
    blocks_out = []
    total_sets = 0
    for block in blocks:
        prescs = [_build_prescription(ex, catalogue) for ex in block["exercises"]]
        total_sets += sum(len(p["sets"]) for p in prescs)
        blocks_out.append(
            {
                "id": _u(),
                "blockType": block.get("type", "SingleExercise"),
                "title": block.get("title"),
                "coachNotes": block.get("notes"),
                "prescriptions": prescs,
            }
        )
    return {
        "id": _u(),
        "workoutType": "StructuredStrength",
        "calendarId": athlete_id,
        "title": title,
        "prescribedDate": date,
        "instructions": instructions,
        "blocks": blocks_out,
        "snapshot": {
            "totalBlocks": len(blocks_out),
            "completedBlocks": 0,
            "totalSets": total_sets,
            "completedSets": 0,
        },
    }


# ── Auth boilerplate (mirrors analyze.py — strength API is a different host) ──


async def _access(client: TPClient) -> tuple[int | None, str | None, dict[str, Any] | None]:
    athlete_id = await client.ensure_athlete_id()
    if not athlete_id:
        return None, None, _err("AUTH_INVALID", "Could not get athlete ID. Re-authenticate.")
    token = await client._ensure_access_token()
    if not token.success:
        return None, None, _err("AUTH_INVALID", token.message or "Failed to obtain access token.")
    access = client._token_cache.access_token
    if not access:
        return None, None, _err("AUTH_INVALID", "No access token available. Re-authenticate.")
    return athlete_id, access, None


def _headers(access: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://app.trainingpeaks.com",
        "Referer": "https://app.trainingpeaks.com/",
    }


def _map_status(status: int, body: str) -> dict[str, Any]:
    if status == 401:
        return _err("AUTH_EXPIRED", "Session expired. Run 'tp-mcp auth' to re-authenticate.")
    if status == 403:
        return _err("AUTH_INVALID", "Access denied. Check permissions or re-authenticate.")
    if status == 404:
        return _err("NOT_FOUND", "Strength workout not found.")
    if status == 429:
        return _err("RATE_LIMITED", "Rate limited. Please wait before retrying.")
    return _err("API_ERROR", f"Strength API error: {status} {body[:200]}")


# ── Tools ───────────────────────────────────────────────────────────────────


async def tp_create_strength_workout(
    date: str,
    title: str,
    blocks: list[dict[str, Any]],
    instructions: str | None = None,
) -> dict[str, Any]:
    """Create a structured strength (gym) workout on the athlete's calendar.

    Args:
        date: Planned date, YYYY-MM-DD.
        title: Workout title (e.g. "Upper Body").
        blocks: Ordered list of blocks. Each block is
            {"type": "WarmUp"|"SingleExercise"|"Superset"|"Circuit"|"CoolDown",
             "title": optional, "notes": optional,
             "exercises": [{"id": "<library id from tp_search_exercises>",
                            "notes": optional,
                            "sets": [{"Reps": "10", "WeightKg": "60"}, ...]}]}.
            Set values are a map of parameter name → value (strings or numbers).
            Weight unit is the caller's choice (WeightKg / WeightLb / …).
            For Superset / Circuit blocks every exercise must have the same
            number of sets.
        instructions: Optional free-text instructions for the whole session.

    Returns:
        Dict with the created `workout_id`, date, title, and block/set counts.
    """
    if not str(date).strip():
        return _err("VALIDATION_ERROR", "date is required (YYYY-MM-DD).")
    if not str(title).strip():
        return _err("VALIDATION_ERROR", "title is required.")
    if not isinstance(blocks, list):
        return _err("VALIDATION_ERROR", "blocks must be a list.")
    invalid = _validate_blocks(blocks)
    if invalid:
        return _err("VALIDATION_ERROR", invalid)

    async with TPClient() as client:
        athlete_id, access, err = await _access(client)
        if err:
            return err
        payload = _build_payload(athlete_id, date.strip(), title.strip(), blocks, instructions)
        try:
            async with httpx.AsyncClient(timeout=STRENGTH_TIMEOUT) as h:
                r = await h.post(
                    f"{STRENGTH_API_BASE}/rx/activity/v1/workouts/save",
                    headers=_headers(access),
                    json=payload,
                )
        except httpx.TimeoutException:
            return _err("NETWORK_ERROR", "Strength create timed out.")
        except httpx.RequestError:
            logger.exception("Network error creating strength workout")
            return _err("NETWORK_ERROR", "A network error occurred.")

        if r.status_code != 200:
            body = r.text
            # Surface the server's field-level validation verbatim — it is precise.
            try:
                errs = r.json().get("errors")
                if errs:
                    return _err("API_ERROR", f"Strength API rejected the workout: {errs}")
            except Exception:
                pass
            return _map_status(r.status_code, body)

        data = r.json().get("data", {})
        snap = data.get("snapshot") or payload["snapshot"]
        return {
            "workout_id": str(data.get("id")),
            "date": date.strip(),
            "title": title.strip(),
            "total_blocks": snap.get("totalBlocks"),
            "total_sets": snap.get("totalSets"),
        }


async def tp_get_strength_summary(workout_id: str) -> dict[str, Any]:
    """Get a strength workout's compliance summary (blocks / sets completed).

    Args:
        workout_id: The strength workout ID (from tp_create_strength_workout).

    Returns:
        Dict with compliance state/percent and block/prescription/set totals.
    """
    wid = str(workout_id).strip()
    if not wid:
        return _err("VALIDATION_ERROR", "workout_id is required.")
    async with TPClient() as client:
        _, access, err = await _access(client)
        if err:
            return err
        try:
            async with httpx.AsyncClient(timeout=STRENGTH_TIMEOUT) as h:
                r = await h.get(
                    f"{STRENGTH_API_BASE}/rx/activity/v1/workouts/{wid}/summary",
                    headers=_headers(access),
                )
        except httpx.TimeoutException:
            return _err("NETWORK_ERROR", "Strength summary timed out.")
        except httpx.RequestError:
            logger.exception("Network error reading strength summary")
            return _err("NETWORK_ERROR", "A network error occurred.")

        if r.status_code != 200:
            return _map_status(r.status_code, r.text)
        d = r.json().get("data", {})
        return {
            "workout_id": wid,
            "compliance_state": d.get("complianceState"),
            "compliance_percent": d.get("compliancePercent"),
            "total_blocks": d.get("totalBlocks"),
            "completed_blocks": d.get("completedBlocks"),
            "total_prescriptions": d.get("totalPrescriptions"),
            "completed_prescriptions": d.get("completedPrescriptions"),
            "total_sets": d.get("totalSets"),
            "completed_sets": d.get("completedSets"),
            "rpe": d.get("rpe"),
            "feel": d.get("feel"),
        }


async def tp_delete_strength_workout(workout_id: str) -> dict[str, Any]:
    """Delete a strength workout.

    Args:
        workout_id: The strength workout ID to delete.

    Returns:
        Dict confirming deletion.
    """
    wid = str(workout_id).strip()
    if not wid:
        return _err("VALIDATION_ERROR", "workout_id is required.")
    async with TPClient() as client:
        _, access, err = await _access(client)
        if err:
            return err
        try:
            async with httpx.AsyncClient(timeout=STRENGTH_TIMEOUT) as h:
                r = await h.delete(
                    f"{STRENGTH_API_BASE}/rx/activity/v1/workouts/{wid}",
                    headers=_headers(access),
                )
        except httpx.TimeoutException:
            return _err("NETWORK_ERROR", "Strength delete timed out.")
        except httpx.RequestError:
            logger.exception("Network error deleting strength workout")
            return _err("NETWORK_ERROR", "A network error occurred.")

        if r.status_code not in (200, 204):
            return _map_status(r.status_code, r.text)
        return {"deleted": True, "workout_id": wid}
