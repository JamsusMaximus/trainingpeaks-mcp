# Targets check — Mini Hopkin's Intervals (NM Sprints) (1:00)

Date: 2026-10-16. Read-only: GET requests only, run with `TP_MCP_READ_ONLY=1`. Nothing was written to TrainingPeaks.

Calls made:
- `GET /fitness/v6/athletes/{id}/workouts/{workoutId}`, once for each athlete
- `GET /exerciselibrary/v2/libraries`
- `GET /exerciselibrary/v2/libraries/{id}/items` for each library, to find item 11440512

## How TrainingPeaks encodes target type

A target object holds `minValue`/`maxValue` and may also hold a `unit`. When `unit` is **missing**, TrainingPeaks reads the target in the workout's `primaryIntensityMetric`. That metric is `percentOfFtp` for all three copies below. When `unit` is `roundOrStridePerMinute`, the target is cadence (rpm). None of the three copies has an HR or RPE target, and no copy uses an absolute-watts unit.

## Hannes Kotze — workout 3979405260 (athlete 2405594)

`workoutDay` 2026-10-06, `lastModifiedDate` 2026-10-06T09:44:31.
Structure header: `primaryIntensityMetric: percentOfFtp`, `primaryLengthMetric: duration`, `fromLegacy: false`, `legacyExercises: []`.

| Block | Step | Length | intensityClass | Target 1 | Target 2 |
|---|---|---|---|---|---|
| step ×1 | Easy (open duration) | 1800 s | warmUp | 35–72, no unit → **% FTP** | — |
| repetition ×6 | Torque | 30 s | active | 95–105, no unit → **% FTP** | 35–45, **no unit → reads as % FTP** |
| | Sprint | 30 s | active | min 150, no unit → **% FTP** | 100–110, **no unit → reads as % FTP** |
| | Rest (open duration) | 300 s | rest | 0–72, no unit → **% FTP** | — |
| step ×1 | Easy | 1500 s | coolDown | 35–72, no unit → **% FTP** | — |

**Power targets present: yes.** Every step has a % FTP target.
**Cadence targets: none.** In Hannes's copy the second target on Torque and Sprint has **no `unit`**. TrainingPeaks therefore reads it as a second % FTP range (35–45 % and 100–110 % FTP), not as rpm. The other two copies carry the cadence unit on these same targets.

Hannes's structure is also serialised differently from the other two. It has float values (`1800.0`), extra `fromLegacy`/`legacyExercises` keys, no `begin`/`end`, and no `type` on inner steps. The structure was re-saved on 2026-10-06 at 09:44, so something re-wrote it, and that re-save is when the cadence units disappeared. This check does not show what did the re-save.

## Donovan — workout 3979516844 (athlete 1536862)

`workoutDay` 2026-10-05, `lastModifiedDate` 2026-10-04T23:14:32.
Structure header: `primaryIntensityMetric: percentOfFtp`, `primaryLengthMetric: duration`.

| Block | Step | Length | intensityClass | Target 1 | Target 2 |
|---|---|---|---|---|---|
| step ×1 (0–1800) | Easy (open duration) | 1800 s | warmUp | 35–72, no unit → **% FTP** | — |
| repetition ×6 (1800–3960) | Torque | 30 s | active | 95–105, no unit → **% FTP** | 35–45 `roundOrStridePerMinute` → **cadence (rpm)** |
| | Sprint | 30 s | active | min 150, no unit → **% FTP** | 100–110 `roundOrStridePerMinute` → **cadence (rpm)** |
| | Rest (open duration) | 300 s | rest | 0–72, no unit → **% FTP** | — |
| step ×1 (3960–5460) | Easy | 1500 s | coolDown | 35–72, no unit → **% FTP** | — |

**Power targets present: yes.** Every step has a % FTP target. Torque and Sprint also have cadence targets.

## Library access in the fork

**Yes.** The fork reads the coach's workout library separately from scheduled workouts:

- `tp_get_libraries` → `GET /exerciselibrary/v2/libraries`
- `tp_get_library_items(library_id)` → `GET /exerciselibrary/v2/libraries/{id}/items`
- `tp_get_library_item(library_id, item_id)` → returns the full item, including its structure

All three are in `src/tp_mcp/tools/library.py`. Scheduled workouts use the separate `/fitness/v6/athletes/{id}/workouts` endpoints (`tp_get_workout` / `tp_get_workouts`).

## Library template 11440512

Library "Torque / Low cadence " (id 1026387). Item type `WorkoutTemplate`, `workoutTypeId` 2 (bike), name "Mini Hopkin's Intervals (NM Sprints) (1:00)", TSS 67.6, IF 0.67, 1:31 planned.
Structure header: `primaryIntensityMetric: percentOfFtp`, `primaryLengthMetric: duration`.

| Step | Target 1 | Target 2 |
|---|---|---|
| Easy warm-up 1800 s | 35–72 → **% FTP** | — |
| Torque 30 s (×6) | 95–105 → **% FTP** | 35–45 `roundOrStridePerMinute` → **cadence** |
| Sprint 30 s (×6) | min 150 → **% FTP** | 100–110 `roundOrStridePerMinute` → **cadence** |
| Rest 300 s (×6) | 0–72 → **% FTP** | — |
| Easy cool-down 1500 s | 35–72 → **% FTP** | — |

The library copy carries **% FTP (power) and cadence** targets only, with no HR, RPE or absolute watts. Donovan's scheduled copy matches it exactly, `begin`/`end` offsets included. Hannes's copy matches on steps and values but has lost the cadence `unit` on the two Torque/Sprint secondary targets.
