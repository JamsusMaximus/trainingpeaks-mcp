#!/usr/bin/env python3
# ruff: noqa: E501
"""Capture output shapes of every tool against the real TrainingPeaks API.

The committed result (tests/fixtures/tool_shapes_baseline.json) is the
regression oracle for the SDK v2 migration (PRD PR 3): re-run this script on
the migrated server and diff - zero shape deltas expected, every delta must be
explained in the PR.

How it works
- Calls tools through ``call_tool`` (the server dispatch layer), so the shape
  includes exactly what an MCP client receives.
- Reads run against live data. Writes run against clearly-marked scratch
  entities (titles prefixed "TPMCP BASELINE SCRATCH", dated June 2030) which
  are deleted before the script exits; settings writes round-trip the current
  value unchanged. Tools that cannot be exercised safely are recorded as
  skipped WITH the reason - nothing is dropped silently.
- Shapes, not values: every leaf collapses to its JSON type name, dict keys are
  sorted, list elements are merged (union of keys / union of leaf types), so
  IDs, dates and metric values never churn the baseline.

Usage:  uv run python scripts/capture_tool_shapes.py [--out PATH]
Needs a valid credential (tp-mcp auth-status must pass) on a personal account.
"""

import argparse
import asyncio
import json
import sys
from datetime import date, timedelta
from importlib.metadata import version
from pathlib import Path
from typing import Any

from tp_mcp.server import TOOLS, call_tool

SCRATCH = "TPMCP BASELINE SCRATCH"
D = "2030-06-{:02d}"  # far-future scratch dates
OUT_DEFAULT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "tool_shapes_baseline.json"

# Tools deliberately not exercised. Every entry needs a reason - the baseline
# records these so the PR 3 sweep knows they have no oracle.
DELIBERATE_SKIPS = {
    "tp_refresh_auth": "interactive browser cookie extraction",
    "tp_pair_workout": "needs a device-paired planned+completed workout pair",
    "tp_unpair_workout": "needs a device-paired workout",
    "tp_apply_training_plan": "bulk-creates a full plan of workouts on the real calendar",
    "tp_log_metrics": "metric datapoints have no delete API - would permanently pollute real data",
    "tp_create_zones": "overwrites real zone settings and no API reads them back for restore",
    "tp_update_speed_zones": "cannot safely round-trip current threshold paces as input strings",
}


def _merge_shapes(a: Any, b: Any) -> Any:
    if isinstance(a, dict) and isinstance(b, dict):
        return {k: (_merge_shapes(a[k], b[k]) if k in a and k in b else a.get(k, b.get(k))) for k in sorted(set(a) | set(b))}
    if isinstance(a, list) and isinstance(b, list):
        items = [x for x in a + b if x != "empty"]
        out = items[0] if items else "empty"
        for it in items[1:]:
            out = _merge_shapes(out, it)
        return [out]
    if a == b:
        return a
    return "|".join(sorted(set(str(a).split("|")) | set(str(b).split("|"))))


def shape_of(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: shape_of(v[k]) for k in sorted(v)}
    if isinstance(v, list):
        if not v:
            return ["empty"]
        out: Any = shape_of(v[0])
        for item in v[1:]:
            out = _merge_shapes(out, shape_of(item))
        return [out]
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    return type(v).__name__


class Runner:
    def __init__(self) -> None:
        self.results: dict[str, dict[str, Any]] = {}
        self.ctx: dict[str, Any] = {}
        self.cleanup_failures: list[str] = []

    async def call(self, tool: str, args: dict[str, Any] | None = None) -> Any:
        """Invoke through the dispatch layer; return the parsed payload."""
        contents = await call_tool(tool, dict(args or {}))
        payload = json.loads(contents[0].text)
        return payload

    async def capture(self, tool: str, args: dict[str, Any] | None = None, *, variant: str = "") -> Any:
        """Capture the shape for ``tool`` (first success wins). Returns payload or None."""
        try:
            payload = await self.call(tool, args)
        except Exception as e:  # noqa: BLE001 - a capture must never kill the run
            self.results.setdefault(tool, {"skipped": f"exception during capture: {type(e).__name__}: {e}"})
            return None
        if isinstance(payload, dict) and payload.get("isError"):
            self.results.setdefault(
                tool, {"skipped": f"API error {payload.get('error_code')}: {str(payload.get('message'))[:120]}"}
            )
            return None
        entry = {"shape": shape_of(payload)}
        if variant:
            entry["variant"] = variant
        self.results[tool] = entry
        return payload

    async def cleanup(self, tool: str, args: dict[str, Any]) -> None:
        """Delete a scratch entity; capture the delete shape as a bonus."""
        payload = await self.capture(tool, args)
        if payload is None:
            self.cleanup_failures.append(f"{tool}({args})")


async def main(out_path: Path) -> int:
    r = Runner()
    today = date.today()
    recent_start = (today - timedelta(days=89)).isoformat()
    recent_end = today.isoformat()

    # --- independent reads ---------------------------------------------------
    auth = await r.capture("tp_auth_status")
    if not auth:
        print("FATAL: auth check failed - run tp-mcp auth-status first", file=sys.stderr)
        return 1
    await r.capture("tp_get_profile")
    await r.capture("tp_get_workout_types")
    await r.capture("tp_get_zone_methods")
    settings = await r.capture("tp_get_athlete_settings")
    await r.capture("tp_get_pool_length_settings")
    await r.capture("tp_get_fitness", {"days": 30})
    await r.capture("tp_get_weekly_summary")
    await r.capture("tp_get_atp", {"start_date": recent_start, "end_date": recent_end})
    await r.capture("tp_get_metrics", {"start_date": recent_start, "end_date": recent_end})
    await r.capture("tp_get_nutrition", {"start_date": recent_end, "end_date": recent_end})
    await r.capture("tp_get_peaks", {"sport": "Bike", "pr_type": "power20min", "days": 90})
    await r.capture("tp_get_focus_event")
    await r.capture("tp_get_next_event")
    await r.capture("tp_list_groups")
    await r.capture("tp_list_athletes")
    await r.capture("tp_search_exercises", {"query": "squat", "limit": 3})
    await r.capture(
        "tp_validate_structure",
        {"structure": json.dumps({"steps": [{"name": "warmup", "duration_seconds": 600, "intensity_min": 50, "intensity_max": 60}]})},
    )
    await r.capture("tp_get_strength_workouts", {"start_date": recent_start, "end_date": recent_end})

    workouts = await r.capture("tp_get_workouts", {"start_date": recent_start, "end_date": recent_end, "type": "completed"})
    completed_id = None
    for w in (workouts or {}).get("workouts", []):
        if w.get("id") and (w.get("duration_actual") or w.get("distance_actual_km")):
            completed_id = str(w["id"])
            break
    if completed_id:
        await r.capture("tp_analyze_workout", {"workout_id": completed_id})
        await r.capture("tp_get_workout_prs", {"workout_id": completed_id})
    else:
        r.results["tp_analyze_workout"] = {"skipped": "no completed workout found in the last 89 days"}
        r.results["tp_get_workout_prs"] = {"skipped": "no completed workout found in the last 89 days"}

    # --- training plans (read-only; apply is a deliberate skip) --------------
    plans = await r.capture("tp_list_training_plans")
    plan_id = ((plans or {}).get("plans") or [{}])[0].get("plan_id")
    if plan_id:
        await r.capture("tp_get_training_plan", {"plan_id": plan_id})
        await r.capture("tp_get_training_plan_workouts", {"plan_id": plan_id})
    else:
        r.results["tp_get_training_plan"] = {"skipped": "account has no authored training plans"}
        r.results["tp_get_training_plan_workouts"] = {"skipped": "account has no authored training plans"}

    # --- workout scratch chain ----------------------------------------------
    w1 = await r.capture(
        "tp_create_workout",
        {"date": D.format(1), "sport": "Run", "title": f"{SCRATCH} w1", "duration_minutes": 60, "description": "scratch"},
    )
    w1_id = str((w1 or {}).get("workout_id") or "") or None
    w3_id = w2_id = None
    if w1_id:
        await r.capture("tp_update_workout", {"workout_id": w1_id, "title": f"{SCRATCH} w1 updated"})
        await r.capture("tp_add_workout_comment", {"workout_id": w1_id, "comment": f"{SCRATCH} comment"})
        await r.capture("tp_set_workout_note", {"workout_id": w1_id, "note": f"{SCRATCH} note"})
        await r.capture("tp_get_workout_note", {"workout_id": w1_id})
        await r.capture("tp_get_workout", {"workout_id": w1_id})
        await r.capture("tp_get_workout_comments", {"workout_id": w1_id})
        w2 = await r.capture("tp_copy_workout", {"workout_id": w1_id, "target_date": D.format(2)})
        w2_id = str((w2 or {}).get("workout_id") or "") or None
        w3 = await r.call("tp_create_workout", {"date": D.format(1), "sport": "Bike", "title": f"{SCRATCH} w3", "duration_minutes": 30})
        w3_id = str(w3.get("workout_id") or "") or None if isinstance(w3, dict) and not w3.get("isError") else None
        if w3_id:
            await r.capture("tp_reorder_workouts", {"workout_ids": [w3_id, w1_id]})
        else:
            r.results["tp_reorder_workouts"] = {"skipped": "second scratch workout could not be created"}
        gpx = Path("/tmp/tpmcp_baseline_scratch.gpx")
        gpx.write_text(
            '<?xml version="1.0"?><gpx version="1.1" creator="tpmcp-baseline">'
            '<trk><name>scratch</name><trkseg>'
            '<trkpt lat="51.5" lon="-0.1"><time>2030-06-01T09:00:00Z</time></trkpt>'
            '<trkpt lat="51.5001" lon="-0.1"><time>2030-06-01T09:00:10Z</time></trkpt>'
            '</trkseg></trk></gpx>'
        )
        up = await r.capture(
            "tp_upload_workout_file",
            {"workout_id": w1_id, "file_path": str(gpx), "workout_day": D.format(1)},
        )
        file_id = (up or {}).get("file_id") or (up or {}).get("fileId")
        if file_id:
            await r.capture("tp_download_workout_file", {"workout_id": w1_id, "file_id": str(file_id)})
            await r.cleanup("tp_delete_workout_file", {"workout_id": w1_id, "file_id": str(file_id)})
        else:
            r.results.setdefault("tp_download_workout_file", {"skipped": "no attachment available (upload not captured)"})
            r.results.setdefault("tp_delete_workout_file", {"skipped": "no attachment available (upload not captured)"})
    else:
        for t in ("tp_update_workout", "tp_add_workout_comment", "tp_set_workout_note", "tp_get_workout_note",
                  "tp_get_workout", "tp_get_workout_comments", "tp_copy_workout", "tp_reorder_workouts",
                  "tp_upload_workout_file", "tp_download_workout_file", "tp_delete_workout_file"):
            r.results.setdefault(t, {"skipped": "scratch workout could not be created"})

    # --- note scratch chain --------------------------------------------------
    note = await r.capture("tp_create_note", {"date": D.format(1), "title": f"{SCRATCH} note", "description": "scratch"})
    note_id = str((note or {}).get("note_id") or "") or None
    if note_id:
        await r.capture("tp_get_note", {"note_id": note_id})
        await r.capture("tp_update_note", {"note_id": note_id, "description": "scratch updated"})
        await r.capture("tp_add_note_comment", {"note_id": note_id, "comment": f"{SCRATCH} comment"})
        await r.capture("tp_get_note_comments", {"note_id": note_id})
        await r.capture("tp_list_notes", {"start_date": D.format(1), "end_date": D.format(28)})
    else:
        for t in ("tp_get_note", "tp_update_note", "tp_add_note_comment", "tp_get_note_comments"):
            r.results.setdefault(t, {"skipped": "scratch note could not be created"})
        await r.capture("tp_list_notes", {"start_date": recent_start, "end_date": recent_end})

    # --- event scratch chain -------------------------------------------------
    # events: tp_update_event resolves ids by searching +/-730 days from today,
    # so the scratch event must sit inside that window (not in 2030)
    ev_date = (today + timedelta(days=400)).isoformat()
    ev = await r.capture("tp_create_event", {"name": f"{SCRATCH} race", "date": ev_date, "event_type": "running"})
    ev_id = str((ev or {}).get("event_id") or "") or None
    if ev_id:
        await r.capture("tp_update_event", {"event_id": ev_id, "description": "scratch updated"})
    else:
        r.results.setdefault("tp_update_event", {"skipped": "scratch event could not be created"})
    await r.capture("tp_get_events", {"start_date": ev_date, "end_date": ev_date})

    # --- equipment scratch chain ---------------------------------------------
    eq = await r.capture("tp_create_equipment", {"name": f"{SCRATCH} shoes", "type": "shoe"})
    eq_id = str((eq or {}).get("equipment_id") or "") or None
    if eq and not eq_id:
        # create returns no id - try to find the scratch item in the list
        eq_list = await r.call("tp_get_equipment", {"type": "all"})
        for item in (eq_list or {}).get("equipment", []) if isinstance(eq_list, dict) else []:
            if SCRATCH in str(item.get("name", "")):
                eq_id = str(item.get("equipment_id") or item.get("id") or "") or None
                break
    if eq and not eq_id:
        r.results.setdefault("tp_update_equipment", {"skipped": "create reports success but returns no id and item never appears in the list - cannot target"})
        r.results.setdefault("tp_delete_equipment", {"skipped": "create reports success but returns no id and item never appears in the list - cannot target"})
    if eq_id:
        await r.capture("tp_update_equipment", {"equipment_id": eq_id, "notes": "scratch updated"})
    else:
        r.results.setdefault("tp_update_equipment", {"skipped": "scratch equipment could not be created"})
    await r.capture("tp_get_equipment", {"type": "all"})

    # --- group scratch chain (membership round-trip on the scratch group) ----
    grp = await r.capture("tp_create_group", {"name": f"{SCRATCH} group"})
    grp_id = str((grp or {}).get("group_id") or "") or None
    athletes = await r.call("tp_list_athletes", {})
    first_athlete = None
    if isinstance(athletes, dict) and not athletes.get("isError"):
        for a in athletes.get("athletes", []):
            if a.get("athlete_id"):
                first_athlete = str(a["athlete_id"])
                break
    if grp_id:
        await r.capture("tp_rename_group", {"group_id": grp_id, "name": f"{SCRATCH} group renamed"})
        await r.capture("tp_list_athletes_in_group", {"group_id": grp_id})
        if first_athlete:
            await r.capture("tp_add_athletes_to_group", {"group_id": grp_id, "athletes": [first_athlete]})
            await r.capture("tp_remove_athletes_from_group", {"group_id": grp_id, "athletes": [first_athlete]})
        else:
            r.results.setdefault("tp_add_athletes_to_group", {"skipped": "no athlete in roster to round-trip"})
            r.results.setdefault("tp_remove_athletes_from_group", {"skipped": "no athlete in roster to round-trip"})
    else:
        for t in ("tp_rename_group", "tp_list_athletes_in_group", "tp_add_athletes_to_group", "tp_remove_athletes_from_group"):
            r.results.setdefault(t, {"skipped": "scratch group could not be created"})

    # --- library scratch chain -----------------------------------------------
    lib = await r.capture("tp_create_library", {"name": f"{SCRATCH} library"})
    lib_id = str((lib or {}).get("library_id") or "") or None
    sched_workout_id = None
    if lib_id:
        item = await r.capture(
            "tp_create_library_item",
            {"library_id": lib_id, "name": f"{SCRATCH} item", "sport_family_id": 2, "sport_type_id": 3,
             "duration_hours": 1.0, "tss": 50},
        )
        item_id = str((item or {}).get("item_id") or "") or None
        if item_id:
            await r.capture("tp_get_library_items", {"library_id": lib_id})
            await r.capture("tp_get_library_item", {"library_id": lib_id, "item_id": item_id})
            await r.capture("tp_update_library_item", {"library_id": lib_id, "item_id": item_id, "tss": 55})
            sched = await r.capture("tp_schedule_library_workout", {"library_id": lib_id, "item_id": item_id, "date": D.format(3)})
            sched_workout_id = str((sched or {}).get("workout_id") or "") or None
        else:
            for t in ("tp_get_library_items", "tp_get_library_item", "tp_update_library_item", "tp_schedule_library_workout"):
                r.results.setdefault(t, {"skipped": "scratch library item could not be created"})
    else:
        for t in ("tp_create_library_item", "tp_get_library_items", "tp_get_library_item", "tp_update_library_item",
                  "tp_schedule_library_workout"):
            r.results.setdefault(t, {"skipped": "scratch library could not be created"})
    await r.capture("tp_get_libraries")

    # --- availability scratch chain ------------------------------------------
    av = await r.capture("tp_create_availability", {"start_date": D.format(10), "end_date": D.format(11), "limited": False})
    av_id = str((av or {}).get("availability_id") or "") or None
    await r.capture("tp_get_availability", {"start_date": D.format(1), "end_date": D.format(28)})

    # --- strength scratch chain ----------------------------------------------
    ex = await r.call("tp_search_exercises", {"query": "squat", "limit": 1})
    ex_id = None
    if isinstance(ex, dict) and not ex.get("isError"):
        hits = ex.get("exercises") or ex.get("results") or []
        if hits:
            ex_id = hits[0].get("id")
    st_id = None
    if ex_id:
        st = await r.capture(
            "tp_create_strength_workout",
            {"date": D.format(5), "title": f"{SCRATCH} strength",
             "blocks": [{"type": "SingleExercise",
                         "exercises": [{"id": ex_id, "sets": [{"Reps": "5"}, {"Reps": "5"}, {"Reps": "5"}]}]}]},
        )
        st_id = str((st or {}).get("workout_id") or "") or None
        if st_id:
            await r.capture("tp_get_strength_workout", {"workout_id": st_id})
            await r.capture("tp_get_strength_summary", {"workout_id": st_id})
    if not st_id:
        for t in ("tp_create_strength_workout", "tp_get_strength_workout", "tp_get_strength_summary"):
            r.results.setdefault(t, {"skipped": "scratch strength workout could not be created"})

    # --- settings round-trips (write current value back, unchanged) ----------
    s = (settings or {})
    ftp = s.get("ftp") or (s.get("power") or {}).get("ftp") or (s.get("bike") or {}).get("ftp")
    if ftp:
        await r.capture("tp_update_ftp", {"ftp": int(ftp)})
    else:
        r.results.setdefault("tp_update_ftp", {"skipped": "current FTP not exposed by tp_get_athlete_settings - no safe round-trip"})
    thr = s.get("threshold_hr") or (s.get("heart_rate") or {}).get("threshold_hr")
    if thr:
        await r.capture("tp_update_hr_zones", {"threshold_hr": int(thr)})
    else:
        r.results.setdefault("tp_update_hr_zones", {"skipped": "current threshold HR not exposed by tp_get_athlete_settings - no safe round-trip"})
    nutrition_today = await r.call("tp_get_nutrition", {"start_date": recent_end, "end_date": recent_end})
    cals = None
    if isinstance(nutrition_today, dict) and not nutrition_today.get("isError"):
        days = nutrition_today.get("days") or nutrition_today.get("nutrition") or []
        if days and isinstance(days, list):
            cals = days[0].get("planned_calories")
    if cals:
        await r.capture("tp_update_nutrition", {"planned_calories": int(cals)})
    else:
        r.results.setdefault("tp_update_nutrition", {"skipped": "no existing planned_calories today - no safe round-trip"})

    # --- cleanup (captures the delete shapes) --------------------------------
    if av_id:
        await r.cleanup("tp_delete_availability", {"availability_id": av_id})
    if st_id:
        await r.cleanup("tp_delete_strength_workout", {"workout_id": st_id})
    if lib_id:
        await r.cleanup("tp_delete_library", {"library_id": lib_id})
    if sched_workout_id:
        await r.cleanup("tp_delete_workout", {"workout_id": sched_workout_id})
    if grp_id:
        await r.cleanup("tp_delete_group", {"group_id": grp_id})
    if eq_id:
        await r.cleanup("tp_delete_equipment", {"equipment_id": eq_id})
    if ev_id:
        await r.cleanup("tp_delete_event", {"event_id": ev_id})
    if note_id:
        await r.cleanup("tp_delete_note", {"note_id": note_id})
    for wid in (w3_id, w2_id, w1_id):
        if wid:
            await r.cleanup("tp_delete_workout", {"workout_id": wid})

    # --- deliberate skips + completeness -------------------------------------
    for tool, reason in DELIBERATE_SKIPS.items():
        r.results.setdefault(tool, {"skipped": f"deliberate: {reason}"})
    missing = sorted({t.name for t in TOOLS} - set(r.results))
    for name in missing:
        r.results[name] = {"skipped": "not reached by the capture plan - extend scripts/capture_tool_shapes.py"}

    baseline = {
        "mcp_sdk_version": version("mcp"),
        "tool_count": len(TOOLS),
        "tools": {k: r.results[k] for k in sorted(r.results)},
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n")

    captured = sum(1 for v in r.results.values() if "shape" in v)
    skipped = {k: v["skipped"] for k, v in r.results.items() if "skipped" in v}
    print(f"captured {captured}/{len(TOOLS)} tool shapes -> {out_path}")
    print(f"skipped {len(skipped)}:")
    for k, v in sorted(skipped.items()):
        print(f"  {k}: {v}")
    if r.cleanup_failures:
        print("\nCLEANUP FAILURES - REMOVE MANUALLY ON trainingpeaks.com (June 2030):", file=sys.stderr)
        for f in r.cleanup_failures:
            print(f"  {f}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    sys.exit(asyncio.run(main(ap.parse_args().out)))
