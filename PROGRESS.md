# TrainingPeaks MCP Server - Progress

## Current Phase
MVP - Complete & Tested

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

### API Client (MVP)
- [x] API-01 - HTTP client wrapper
- [x] API-02 - Response parsing models

### Tools (MVP)
- [x] TOOL-01 - tp_auth_status
- [x] TOOL-02 - tp_get_profile
- [x] TOOL-03 - tp_get_workouts (with 90-day limit)
- [x] TOOL-04 - tp_get_workout
- [x] TOOL-05 - tp_get_peaks (sport-specific PRs)
- [x] TOOL-06 - tp_get_workout_prs
- [x] TOOL-07 - tp_get_fitness (CTL/ATL/TSB)

### Server (MVP)
- [x] SERVER-01 - MCP server setup
- [x] SERVER-02 - Python 3.14 async fix

### Testing & Docs (MVP)
- [x] TEST-01 - Integration test suite (30 tests passing)
- [x] DOCS-01 - README with SEO optimization
- [x] DOCS-02 - MIT License

### Future (V1)
- [ ] TOOL-08 - tp_create_workout
- [ ] TOOL-09 - tp_move_workout
- [ ] TEST-02 - Tests for fitness/peaks tools
- [ ] CI-01 - GitHub Actions workflow

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
- 90-day max date range to prevent context bloat
- Tool descriptions optimized for LLM efficiency
