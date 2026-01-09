# TrainingPeaks MCP Server - Progress

## Current Phase
MVP - Complete & Production Ready

## Last Updated
2026-01-09

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
- [x] TEST-01 - Integration test suite (44 tests passing)
- [x] TEST-02 - Tests for fitness/peaks tools
- [x] CI-01 - GitHub Actions workflow (Python 3.10-3.12)
- [x] DOCS-01 - README with SEO optimization (trainingpeaks + training-peaks tags)
- [x] DOCS-02 - MIT License
- [x] DOCS-03 - Example screenshot
- [x] DOCS-04 - Advanced analytics query examples

### Future (V1)
- [ ] TOOL-08 - tp_create_workout
- [ ] TOOL-09 - tp_move_workout
- [ ] TOOL-10 - tp_get_health_metrics (sleep, resting HR, HRV, weight)

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
