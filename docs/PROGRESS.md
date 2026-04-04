# TrainingPeaks MCP Server - Progress

## Current Phase
MVP - Complete & Production Ready

## Last Updated
2026-04-04

## Completed Tasks

### Setup
- [x] SETUP-01 - Project scaffolding

### Authentication (MVP)
- [x] AUTH-01 - Keyring credential storage
- [x] AUTH-02 - Cookie validation
- [x] AUTH-03 - CLI auth command
- [x] AUTH-04 - Encrypted file fallback
- [x] AUTH-05 - Dual storage (keyring + encrypted file) for Claude Desktop compatibility
- [x] AUTH-06 - Browser cookie extraction (--from-browser flag)
- [x] AUTH-07 - Don't auto-clear cookie on 401 (prevents data loss on transient errors)

### API Client (MVP)
- [x] API-01 - HTTP client wrapper
- [x] API-02 - Response parsing models

### Tools (MVP)
- [x] TOOL-01 - tp_auth_status
- [x] TOOL-02 - tp_get_profile
- [x] TOOL-03 - tp_get_workouts (with 90-day limit)
- [x] TOOL-04 - tp_get_workout
- [x] TOOL-05 - tp_get_peaks (sport-specific PRs, default 3650 days for all-time)
- [x] TOOL-06 - tp_get_workout_prs
- [x] TOOL-07 - tp_get_fitness (CTL/ATL/TSB with historical date range support)
- [x] TOOL-08 - tp_refresh_auth (auto-extract cookie from browser)

### CLI
- [x] CLI-01 - tp-mcp config command (outputs Claude Desktop config snippet)

### Server (MVP)
- [x] SERVER-01 - MCP server setup
- [x] SERVER-02 - Python 3.14 async fix

### Testing & Docs (MVP)
- [x] TEST-01 - Integration test suite (338 tests passing)
- [x] TEST-02 - Tests for fitness/peaks tools
- [x] CI-01 - GitHub Actions workflow (Python 3.10-3.14)
- [x] DOCS-01 - README with SEO optimization (trainingpeaks + training-peaks tags)
- [x] DOCS-02 - MIT License
- [x] DOCS-03 - Example screenshot
- [x] DOCS-04 - Advanced analytics query examples

### Future (V1)
- [x] TOOL-08 - tp_create_workout (basic: date, sport, title, duration; structured workouts deferred)
- [x] TOOL-11 - tp_pair_workout (pair completed workout with planned workout via combine endpoint)
- [x] TOOL-12 - tp_unpair_workout (split paired workout into completed + planned via split endpoint)
- [ ] TOOL-09 - tp_move_workout
- [ ] TOOL-10 - tp_get_health_metrics (sleep, resting HR, HRV, weight)

## Recent Changes (2026-04-04)

### Structured Workout Updates (PR #35, #36)
- `tp_update_workout` now accepts the same simplified `structure` format as `tp_create_workout`
- Shared logic refactored into `_prepare_structure_payload` returning a `StructurePayload` NamedTuple (PR #47)
- Native `structured_workout` payload support for raw TrainingPeaks builder round-trip (create, update, get)

### Planned Workout Start Times (PR #34, #48)
- `tp_create_workout` and `tp_update_workout` accept `YYYY-MM-DDTHH:MM:SS` for planned start times
- Date-only updates intelligently shift existing planned start times to preserve time-of-day
- `tp_copy_workout` now preserves `startTimePlanned` when copying workouts

### FTP Update Fix (PR #37)
- Fixed HTTP 500 errors on the powerzones endpoint by sending the full zone array
- Added handling for 204 No Content responses
- Zone boundaries are now scaled proportionally from old to new FTP

### Type and Test Improvements (PR #49, #50)
- Widened `TPClient._request()` json parameter type to accept list payloads
- Added edge-case test coverage for FTP fallback and pair/unpair unexpected responses

## Recent Changes (2026-04-03)

### Pair/Unpair Workout Tools
Added `tp_pair_workout` and `tp_unpair_workout` tools that use the TrainingPeaks
combine/split API endpoints. These allow pairing a completed workout with a planned
workout (merging them into one calendar entry) and unpairing them back into separate
entries. All data is preserved in both directions — comments, metrics, planned fields.

API endpoints discovered by reverse-engineering the TrainingPeaks web app:
- Pair: `POST /fitness/v6/athletes/{id}/commands/workouts/combine`
- Unpair: `POST /fitness/v6/athletes/{id}/commands/workouts/{workoutId}/split`

9 unit tests added. Live tested against a real TrainingPeaks account.

## Recent Changes (2026-01-09)

### Auth Fix for Claude Desktop
macOS Keychain has app-specific access controls. When Claude Desktop spawns `tp-mcp serve`,
it's a different app context than Terminal where `tp-mcp auth` was run. Keychain silently
blocks access, causing auth failures.

**Fix:** `store_credential()` now writes to both keyring AND encrypted file. The encrypted
file fallback always works regardless of app permissions.

### tp_get_peaks Default Changed to All-Time
Previous default of 365 days caused "best" queries to miss PRs older than 1 year.
Now defaults to 3650 days (~10 years) for true all-time records.

### tp_get_fitness Historical Date Ranges
Added `start_date` and `end_date` parameters (YYYY-MM-DD) for querying historical fitness
data. Enables queries like "CTL/ATL/TSB in the 6 weeks before my Feb 2022 PR".

Previously only supported querying from today backwards using `days` parameter.

## API Endpoint Reference

Verified against live TrainingPeaks API (2026-01-09):

| Endpoint | Purpose |
|----------|---------|
| `/users/v3/token` | Auth validation |
| `/users/v3/user` | User profile (nested: `{ user: { personId } }`) |
| `/fitness/v6/athletes/{id}/workouts/{start}/{end}` | Workout list |
| `/fitness/v6/athletes/{id}/workouts/{workoutId}` | Single workout |
| `/fitness/v6/athletes/{id}/commands/workouts/combine` | Pair workouts (POST, body: `{athleteId, completedWorkoutId, plannedWorkoutId}`) |
| `/fitness/v6/athletes/{id}/commands/workouts/{workoutId}/split` | Unpair workout (POST, empty body) |
| `/fitness/v2/athletes/{id}/powerzones` | Power zones (PUT, full array of zone groups) |
| `/personalrecord/v2/athletes/{id}/workouts/{workoutId}` | PRs per workout |
| `/personalrecord/v2/athletes/{id}/{Sport}?prType=...` | Sport-specific PRs |
| `/fitness/v1/athletes/{id}/reporting/performancedata/{start}/{end}` | CTL/ATL/TSB (POST) |

**Deprecated:** `/fitness/v3/athletes/{id}/powerpeaks` and `/pacepeaks` return 404.

## Architecture Decisions

- Pydantic v2 with ConfigDict for models
- Async validation to avoid nested asyncio.run() on Python 3.14
- 90-day max date range for workouts to prevent context bloat
- 3650-day default for peaks (all-time)
- Dual credential storage (keyring + encrypted file) for cross-app compatibility
- Tool descriptions optimized for LLM efficiency
- Line length 120 for readable tool descriptions
