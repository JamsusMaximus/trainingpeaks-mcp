# TrainingPeaks MCP Server - Progress

## Current Phase
MVP - Complete

## Last Completed Task
DOCS-01 - README and examples - 2025-01-08

## Next Task
Ready for human testing / V1 development

## Blockers
None

## Completed Tasks

### Setup
- [x] SETUP-01 - Project scaffolding

### Authentication (MVP)
- [x] AUTH-01 - Keyring credential storage
- [x] AUTH-02 - Cookie validation
- [x] AUTH-03 - CLI auth command
- [x] AUTH-04 - Encrypted file fallback

### API Client (MVP)
- [x] API-01 - HTTP client wrapper
- [x] API-02 - Response parsing models

### Tools (MVP)
- [x] TOOL-01 - tp_auth_status
- [x] TOOL-02 - tp_get_profile
- [x] TOOL-03 - tp_get_workouts
- [x] TOOL-04 - tp_get_workout
- [x] TOOL-05 - tp_get_peaks

### Server (MVP)
- [x] SERVER-01 - MCP server setup

### Testing & Docs (MVP)
- [x] TEST-01 - Integration test suite (30 tests passing)
- [x] DOCS-01 - README and examples

### Tools (V1)
- [ ] TOOL-06 - tp_create_workout
- [ ] TOOL-07 - tp_move_workout
- [ ] TOOL-08 - tp_schedule_workout

### Platform & Security (V1)
- [ ] PLATFORM-01 - Windows support
- [ ] SECURITY-01 - Security audit
- [ ] TEST-02 - E2E test suite

## Architecture Decisions
- Using Pydantic v2 with ConfigDict for models
- Renamed date fields to workout_date/peak_date to avoid type annotation conflicts
- Using property aliases for backwards compatibility

## API Endpoint Discoveries
Verified against live TrainingPeaks API (2026-01-09):
- /users/v3/token - Auth validation
- /users/v3/user - User profile (returns nested: `{ user: { personId, ... } }`)
- /fitness/v6/athletes/{id}/workouts/{start}/{end} - Workout list
- /fitness/v6/athletes/{id}/workouts/{workoutId} - Single workout (v6 not v1!)
- /personalrecord/v2/athletes/{id}/workouts/{workoutId}?displayPeaksForBasic=true - Personal records per workout
- /personalrecord/v2/athletes/{id}/{Sport}?prType=...&startDate=...&endDate=... - Sport-specific PRs by type
- /personalrecord/v2/athletes/{id}/config - PR configuration (available types by sport)
- /fitness/v1/athletes/{id}/reporting/performancedata/{start}/{end} (POST) - CTL/ATL/TSB fitness data
- /fitness/v3/athletes/{id}/powerpeaks - DEPRECATED (returns 404)
- /fitness/v3/athletes/{id}/pacepeaks - DEPRECATED (returns 404)

## Known Issues
- Old peaks endpoints (/powerpeaks, /pacepeaks) deprecated - use /personalrecord/v2/ instead
- RESOLVED: Found correct endpoint via network traffic analysis (2026-01-09)

## Session Notes
MVP implementation complete. Ready for human testing with a real TrainingPeaks account.

Test with:
1. tp-mcp auth (paste your Production_tpAuth cookie)
2. tp-mcp auth-status
3. Configure Claude Desktop and test tools
