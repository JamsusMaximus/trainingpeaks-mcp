# TrainingPeaks MCP Server
## Product Requirements Document

**Version:** 1.1  
**Author:** James  
**Date:** January 2025  
**Status:** Draft

---

## Claude Code Implementation Guide

> **READ THIS FIRST.** This section defines how Claude Code should approach building this project to maintain quality through context compaction.

### Progress Tracking System

**Always maintain `PROGRESS.md` in the project root.** This file survives compaction and is your source of truth.

```markdown
# Project Progress

## Current Phase
MVP / V1 / Complete

## Last Completed Task
[task-id] - Brief description - YYYY-MM-DD HH:MM

## Next Task
[task-id] - Brief description

## Blockers
- None / List any blockers

## Completed Tasks
- [x] [AUTH-01] Keyring storage implementation
- [x] [AUTH-02] Cookie validation
- [ ] [TOOL-01] tp_get_profile tool
...

## Architecture Decisions
- Decision 1: Rationale
- Decision 2: Rationale

## Known Issues
- Issue 1: Description, workaround
```

**Update `PROGRESS.md` after completing each task.** This is non-negotiable.

### Sub-Agent Strategy

Use sub-agents (via `Task`) for isolated, well-defined work. Each sub-agent should:
1. Receive a specific task ID and clear deliverables
2. Have access to relevant files only
3. Return with a status report

**When to spawn sub-agents:**
- Implementing a single tool (one sub-agent per tool)
- Writing tests for a module
- Security audit of a component
- Documentation generation

**When NOT to spawn sub-agents:**
- Cross-cutting concerns (auth affects everything)
- Architectural decisions
- Debugging integration issues

### Task Breakdown

Each task has an ID for tracking. Complete tasks in order within each phase.

#### Phase 1: MVP Tasks

```
SETUP-01: Project scaffolding
  - Create directory structure
  - Initialize pyproject.toml with dependencies
  - Create empty module files
  - Deliverable: Working `pip install -e .` 

AUTH-01: Keyring credential storage
  - Implement keyring read/write for Production_tpAuth
  - Add fallback detection (keyring unavailable)
  - Deliverable: store_credential(), get_credential(), clear_credential()

AUTH-02: Cookie validation
  - HTTP client setup with cookie auth
  - Validate against /users/v3/token
  - Parse athlete_id from response
  - Deliverable: validate_auth() -> AuthResult

AUTH-03: CLI auth command
  - `tp-mcp auth` interactive flow
  - Prompt for cookie paste
  - Validate and store
  - Deliverable: Working auth command

AUTH-04: Encrypted file fallback
  - AES-256-GCM encryption
  - Machine-specific key derivation
  - Proper file permissions
  - Deliverable: EncryptedCredentialStore class

API-01: HTTP client wrapper
  - Async httpx client
  - Automatic auth header injection
  - 401 detection and credential clearing
  - Timeout handling
  - Deliverable: TPClient class

API-02: Response parsing
  - Pydantic models for API responses
  - Minimal field extraction (token efficiency)
  - Deliverable: Models for user, workout, peaks

TOOL-01: tp_auth_status tool
  - MCP tool registration
  - Call validate_auth()
  - Return structured status
  - Deliverable: Working tool, tests

TOOL-02: tp_get_profile tool
  - Fetch /users/v3/user
  - Parse and return minimal fields
  - Deliverable: Working tool, tests

TOOL-03: tp_get_workouts tool
  - Date range parameter handling
  - Fetch /fitness/v6/athletes/{id}/workouts/{start}/{end}
  - Filter by type (all/planned/completed)
  - Deliverable: Working tool, tests

TOOL-04: tp_get_workout tool
  - Single workout fetch
  - Full structure parsing
  - Deliverable: Working tool, tests

TOOL-05: tp_get_peaks tool
  - Power and pace peak endpoints
  - Duration filtering
  - Deliverable: Working tool, tests

SERVER-01: MCP server setup
  - stdio transport configuration
  - Tool registration
  - Startup auth validation
  - Deliverable: `tp-mcp serve` command

TEST-01: Integration test suite
  - Mock API responses
  - Test each tool
  - Test auth flows
  - Deliverable: pytest suite, 80%+ coverage

DOCS-01: README and examples
  - Installation instructions
  - Claude Desktop config
  - Security notes
  - Deliverable: README.md
```

#### Phase 2: V1 Tasks

```
TOOL-06: tp_create_workout tool
  - Workout structure builder
  - Library endpoint integration
  - Deliverable: Working tool, tests

TOOL-07: tp_move_workout tool
  - PUT endpoint for workout update
  - Date validation
  - Deliverable: Working tool, tests

TOOL-08: tp_schedule_workout tool
  - Library to calendar scheduling
  - Deliverable: Working tool, tests

PLATFORM-01: Windows support
  - Test keyring on Windows
  - Path handling fixes
  - Deliverable: Windows CI passing

SECURITY-01: Security audit
  - Verify all checklist items
  - Penetration testing of auth flow
  - Deliverable: Audit report

TEST-02: E2E test suite
  - Real account testing (manual)
  - Document test results
  - Deliverable: E2E test report
```

### Sub-Agent Prompt Template

When spawning a sub-agent, use this structure:

```
Task: [TASK-ID] - [Task Name]

Context:
- Project: TrainingPeaks MCP Server
- Phase: MVP/V1
- This task's role in the system: [brief explanation]

Files to read first:
- PROGRESS.md (check current state)
- [relevant existing files]

Deliverables:
1. [Specific file/function to create]
2. [Tests if applicable]
3. Update to PROGRESS.md marking task complete

Constraints:
- Follow existing code patterns
- No credentials in logs/errors
- Terse tool descriptions (<50 tokens)
- Update PROGRESS.md when done

Do not:
- Modify unrelated files
- Change architecture without documenting in PROGRESS.md
- Skip tests
```

### Recovery After Compaction

When context is compacted, Claude Code should:

1. **Read `PROGRESS.md` first** — This tells you where you are
2. **Read the PRD** — Refresh on requirements and constraints
3. **Check `git log --oneline -20`** — See recent commits
4. **Resume from "Next Task"** in PROGRESS.md

### File Structure Convention

```
trainingpeaks-mcp/
├── PROGRESS.md           # Always read first after compaction
├── README.md
├── pyproject.toml
├── src/
│   └── tp_mcp/
│       ├── __init__.py
│       ├── __main__.py   # CLI entry point
│       ├── auth/
│       │   ├── __init__.py
│       │   ├── keyring.py      # AUTH-01
│       │   ├── encrypted.py    # AUTH-04
│       │   └── validator.py    # AUTH-02
│       ├── client/
│       │   ├── __init__.py
│       │   ├── http.py         # API-01
│       │   └── models.py       # API-02
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── auth_status.py  # TOOL-01
│       │   ├── profile.py      # TOOL-02
│       │   ├── workouts.py     # TOOL-03, TOOL-04
│       │   ├── peaks.py        # TOOL-05
│       │   ├── create.py       # TOOL-06 (V1)
│       │   ├── move.py         # TOOL-07 (V1)
│       │   └── schedule.py     # TOOL-08 (V1)
│       └── server.py           # SERVER-01
└── tests/
    ├── conftest.py
    ├── test_auth/
    ├── test_client/
    └── test_tools/
```

### Commit Convention

```
[TASK-ID] Brief description

- Detail 1
- Detail 2
```

Example:
```
[AUTH-01] Implement keyring credential storage

- Add store_credential(), get_credential(), clear_credential()
- Handle keyring.errors.NoKeyringError gracefully
- Tests passing
```

### Quality Gates

Before marking a task complete:

1. **Code runs** — No syntax errors, imports work
2. **Tests pass** — `pytest tests/` green
3. **Types check** — `mypy src/` clean (if types added)
4. **No credential leaks** — Grep for cookie values, auth tokens
5. **PROGRESS.md updated** — Task checked off, next task identified

---

## Executive Summary

This PRD defines a Model Context Protocol (MCP) server for TrainingPeaks that enables AI assistants to read workout data, create and move workouts, and analyse power/pace peaks. The server uses TrainingPeaks' internal API via session cookie authentication—the only viable path since TrainingPeaks restricts its official API to approved commercial partners.

**Core principles:**
1. **Security first** — Credentials never logged, stored in system keyring, zero plaintext exposure
2. **Token efficient** — Minimal tool count, terse descriptions, lazy loading where possible
3. **Pragmatic** — Cookie-based auth with manual extraction (proven pattern from tp2intervals)
4. **Phased delivery** — Read-only MVP, then write operations in V1

---

## Problem Statement

TrainingPeaks is widely used by endurance athletes and coaches but has no public API for personal use. Existing tools like tp2intervals prove that the internal API (`tpapi.trainingpeaks.com`) works reliably with session cookie authentication. Athletes want to query their training data, analyse performance trends, and manage workouts through AI assistants without switching contexts to the TrainingPeaks web app.

**Why not use existing solutions?**
- AI Endurance MCP requires a separate subscription and syncs via their platform
- tp2intervals is a standalone sync tool, not an MCP server
- No TrainingPeaks MCP server exists

---

## Goals and Non-Goals

### Goals
- Read all workout data (planned and completed) for arbitrary date ranges
- Create structured workouts in the workout library
- Move/reschedule workouts on the calendar
- Analyse peak power and pace data
- Bulletproof credential security — zero chance of leaking user credentials
- Minimal context window consumption (<2,000 tokens for tool definitions)
- Clear re-authentication flow when cookies expire

### Non-Goals
- Coach/athlete relationship management
- Social features or sharing
- Direct Garmin/Strava sync (use native TP integrations)
- Automated cookie extraction from browser (too fragile, security concerns)
- Remote/hosted deployment (local stdio only for MVP/V1)

---

## Technical Architecture

### Authentication Strategy

**Method:** Manual session cookie extraction (tp2intervals pattern)

TrainingPeaks uses the `Production_tpAuth` cookie for API authentication. Users extract this cookie from browser DevTools and provide it to the MCP server. This approach:
- Avoids platform-specific browser decryption code
- Doesn't trigger OS permission prompts
- Has proven reliability (tp2intervals has used it for years)
- Keeps the user in control of their credentials

**Cookie extraction flow:**
1. User logs into TrainingPeaks in browser
2. Opens DevTools → Network tab
3. Navigates to any tpapi.trainingpeaks.com request
4. Copies the `Production_tpAuth` cookie value
5. Runs `tp-mcp auth` CLI command and pastes when prompted
6. Cookie is validated against `/users/v3/token` endpoint
7. On success, stored in system keyring

### Credential Storage Hierarchy

**Primary: System Keyring**
```
Service: trainingpeaks-mcp
Username: production_tpauth
Password: <cookie_value>
```

Uses Python `keyring` library which maps to:
- macOS: Keychain
- Windows: Credential Locker  
- Linux: Secret Service (GNOME Keyring / KWallet)

**Fallback: Encrypted file** (for headless/container environments)
```
~/.config/trainingpeaks-mcp/credentials.enc
```
- AES-256-GCM encryption
- Key derived from machine-specific identifier + user password
- File permissions: `chmod 600`
- Directory permissions: `chmod 700`

**Environment variable override:** `TP_AUTH_COOKIE`
- For CI/testing only
- Documented with security warnings
- Never used if keyring is available

### Security Requirements (Non-Negotiable)

| Requirement | Implementation |
|-------------|----------------|
| No plaintext storage | Keyring primary, encrypted file fallback |
| No credential logging | Redact in all log output, error messages |
| No credential in process args | Read from keyring/file, never CLI args |
| No credential in tool responses | Strip from any API response data |
| Validation on startup | Fail fast if auth invalid |
| Clear expiry handling | Detect 401, prompt re-auth, never retry with bad creds |
| No network exposure | stdio transport only (localhost) |
| Minimal permissions | Read-only mode by default |

**Credential lifecycle:**
```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│ User pastes │────▶│ Validate via │────▶│ Store in    │
│ cookie      │     │ /users/v3/   │     │ keyring     │
└─────────────┘     │ token        │     └─────────────┘
                    └──────────────┘            │
                           │                    ▼
                    ┌──────┴──────┐     ┌─────────────┐
                    │ 401/403?    │◀────│ Load on     │
                    │ Clear creds │     │ server start│
                    │ Prompt re-  │     └─────────────┘
                    │ auth        │
                    └─────────────┘
```

### API Endpoints

Base URL: `https://tpapi.trainingpeaks.com`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/users/v3/token` | GET | Validate auth, get user info |
| `/users/v3/user` | GET | Get athlete ID and profile |
| `/fitness/v6/athletes/{id}/workouts/{start}/{end}` | GET | Fetch workouts by date range |
| `/fitness/v1/athletes/{id}/workouts/{workoutId}` | GET | Get single workout details |
| `/fitness/v1/athletes/{id}/workouts/{workoutId}` | PUT | Update workout (move date) |
| `/exerciselibrary/v1/libraries/{id}/items` | POST | Create workout in library |
| `/fitness/v3/athletes/{id}/powerpeaks` | GET | Power peak data |
| `/fitness/v3/athletes/{id}/pacepeaks` | GET | Pace peak data |

**Note:** Exact endpoints need validation via network traffic analysis. The above are based on tp2intervals and similar tools.

### Transport

**stdio only** — The server runs as a local subprocess spawned by the MCP client (Claude Desktop, etc). This:
- Eliminates network attack surface
- Simplifies deployment
- Matches security-sensitive MCP servers (filesystem, git)
- Avoids SSE/HTTP session management complexity

---

## Tool Design

### Design Principles

Based on MCP best practices research:

1. **Minimal tool count** — 5 tools for MVP, 8 for V1. Fewer tools = better LLM selection accuracy
2. **Terse descriptions** — Under 50 tokens per tool. No verbose explanations
3. **Polymorphic parameters** — One `get_workouts` tool with date filters, not separate tools per query type
4. **Structured responses** — Return only essential fields, not full API responses
5. **Actionable errors** — Tell the LLM how to fix problems, not just what went wrong

### Token Budget

**Target:** <2,000 tokens for all tool definitions

| Component | Token estimate |
|-----------|---------------|
| Tool names + descriptions (8 tools) | ~600 tokens |
| Parameter schemas | ~800 tokens |
| Response type hints | ~400 tokens |
| **Total** | ~1,800 tokens |

Compare to garth-mcp which consumes 66,000+ tokens on init.

### MVP Tools (Read-Only)

#### 1. `tp_get_profile`
```yaml
name: tp_get_profile
description: Get athlete profile and ID
parameters: none
returns: { athlete_id, name, email, account_type }
```

#### 2. `tp_get_workouts`
```yaml
name: tp_get_workouts  
description: Get workouts for date range. Returns planned and completed.
parameters:
  start_date: ISO date (required)
  end_date: ISO date (required)
  type: "all" | "planned" | "completed" (default: "all")
returns: [{ id, date, title, type, sport, duration_planned, duration_actual, tss, description }]
```

#### 3. `tp_get_workout`
```yaml
name: tp_get_workout
description: Get full workout details including structure
parameters:
  workout_id: string (required)
returns: { id, date, title, sport, structure, intervals[], metrics, notes }
```

#### 4. `tp_get_peaks`
```yaml
name: tp_get_peaks
description: Get power or pace peak data
parameters:
  peak_type: "power" | "pace" (required)
  sport: "bike" | "run" (required)  
  duration: "5s" | "1m" | "5m" | "20m" | "60m" | "all" (default: "all")
  days: number of days history (default: 90)
returns: [{ duration, value, date, activity_id }]
```

#### 5. `tp_auth_status`
```yaml
name: tp_auth_status
description: Check auth status. Use when other tools return auth errors.
parameters: none
returns: { valid: bool, athlete_id, expires_hint, action_needed }
```

### V1 Tools (Write Operations)

#### 6. `tp_create_workout`
```yaml
name: tp_create_workout
description: Create structured workout in library
parameters:
  title: string (required)
  sport: "bike" | "run" | "swim" | "strength" | "other" (required)
  duration_minutes: number (required)
  description: string
  structure: workout structure object (intervals, zones, etc)
returns: { workout_id, library_id, title }
```

#### 7. `tp_move_workout`
```yaml
name: tp_move_workout
description: Move workout to different date
parameters:
  workout_id: string (required)
  new_date: ISO date (required)
returns: { success, workout_id, old_date, new_date }
```

#### 8. `tp_schedule_workout`
```yaml
name: tp_schedule_workout
description: Schedule library workout to calendar
parameters:
  library_workout_id: string (required)
  date: ISO date (required)
returns: { scheduled_workout_id, date, title }
```

---

## Error Handling

### Error Response Format

```json
{
  "isError": true,
  "error_code": "AUTH_EXPIRED",
  "message": "Session expired. Run 'tp-mcp auth' to re-authenticate.",
  "recoverable": true,
  "suggested_action": "Call tp_auth_status to confirm, then re-authenticate"
}
```

### Error Codes

| Code | Meaning | LLM Action |
|------|---------|------------|
| `AUTH_EXPIRED` | Cookie expired | Tell user to re-auth |
| `AUTH_INVALID` | Cookie malformed | Tell user to re-auth |
| `NOT_FOUND` | Workout/resource doesn't exist | Check ID, inform user |
| `RATE_LIMITED` | Too many requests | Wait and retry |
| `PREMIUM_REQUIRED` | Feature needs premium account | Inform user |
| `VALIDATION_ERROR` | Bad parameters | Fix parameters |
| `API_ERROR` | TrainingPeaks API issue | Retry or inform user |

### Timeout Handling

- API calls: 30 second timeout
- Auth validation: 10 second timeout
- On timeout: Return error with retry suggestion, don't hang

---

## Development Phases

### Phase 1: MVP (Read-Only)

**Scope:**
- Authentication flow (CLI + keyring storage)
- 5 read-only tools
- stdio transport
- Basic error handling
- macOS + Linux support

**Deliverables:**
1. `tp-mcp` CLI with `auth` and `serve` commands
2. MCP server with 5 tools
3. Claude Desktop configuration example
4. README with setup instructions

**Success criteria:**
- Can authenticate with pasted cookie
- Can query workouts for any date range
- Can retrieve peak power data
- Context consumption <2,000 tokens
- No credential exposure in logs/errors

**Timeline:** 2 weeks

### Phase 2: V1 (Full)

**Scope:**
- 3 additional write tools
- Windows support
- Encrypted file fallback for headless environments
- Premium account detection
- Enhanced workout structure parsing
- Comprehensive test suite

**Deliverables:**
1. Write tools (create, move, schedule)
2. Workout structure builder helpers
3. Premium feature gating
4. Windows keyring support
5. 80%+ test coverage

**Success criteria:**
- Can create structured workouts
- Can move workouts on calendar
- Works on Windows
- Works in Docker (with env var auth)
- No regressions in security

**Timeline:** 3 weeks after MVP

### Future Considerations (V2+)

- Workout templates / presets
- Training plan analysis
- ATL/CTL/TSB calculations
- Integration with intervals.icu for enhanced analytics
- Coach mode (access athlete data with permissions)

---

## Configuration

### Claude Desktop Configuration

```json
{
  "mcpServers": {
    "trainingpeaks": {
      "command": "tp-mcp",
      "args": ["serve"],
      "env": {}
    }
  }
}
```

**Note:** No credentials in config. Server reads from keyring on startup.

### Environment Variables (Advanced)

| Variable | Purpose | Security |
|----------|---------|----------|
| `TP_AUTH_COOKIE` | Override keyring (CI/testing) | ⚠️ Use with caution |
| `TP_MCP_LOG_LEVEL` | Debug logging | Safe |
| `TP_MCP_TIMEOUT` | API timeout seconds | Safe |
| `TP_MCP_READ_ONLY` | Force read-only mode | Safe (default: true for MVP) |

---

## Security Audit Checklist

### Pre-Release Requirements

- [ ] No credentials in git history
- [ ] No credentials logged at any log level
- [ ] No credentials in error messages
- [ ] No credentials in tool responses
- [ ] Keyring storage working on macOS/Linux/Windows
- [ ] Encrypted fallback file has correct permissions
- [ ] 401 responses clear stored credentials
- [ ] No network listeners (stdio only)
- [ ] Dependencies audited for vulnerabilities
- [ ] README includes security considerations

### Ongoing

- [ ] Dependency updates monitored
- [ ] No new logging of sensitive data
- [ ] Auth flow tested after TrainingPeaks changes

---

## Testing Strategy

### Unit Tests
- Cookie validation logic
- Response parsing
- Error code mapping
- Date range handling

### Integration Tests (with mock API)
- Full auth flow
- Each tool's happy path
- Error scenarios (401, 404, timeout)
- Rate limit handling

### End-to-End Tests (manual, with real account)
- Complete auth flow
- Query real workout data
- Create test workout (premium account)
- Move workout
- Verify no credential leaks in logs

### Security Tests
- Verify keyring storage
- Verify file permissions on encrypted fallback
- Verify no credentials in process listing
- Verify no credentials in crash dumps

---

## Dependencies

### Runtime
- Python 3.10+
- `mcp` — Official MCP Python SDK
- `httpx` — Async HTTP client
- `keyring` — Cross-platform credential storage
- `cryptography` — For encrypted file fallback
- `pydantic` — Request/response validation

### Development
- `pytest` — Testing
- `pytest-asyncio` — Async test support
- `ruff` — Linting
- `mypy` — Type checking

### Minimal dependency principle
No heavy frameworks. No browser automation. No GUI libraries.

---

## Open Questions

1. **Exact peak data endpoints** — Need to verify via network traffic analysis
2. **Cookie expiration timing** — How long do Production_tpAuth cookies last?
3. **Rate limits** — What are TrainingPeaks' internal API rate limits?
4. **Workout structure format** — Exact JSON schema for structured workouts
5. **Premium feature boundaries** — Which operations require premium?

---

## Appendix A: TrainingPeaks Account Limitations

| Feature | Free | Premium |
|---------|------|---------|
| View workouts | ✓ | ✓ |
| Plan workouts (today/tomorrow) | ✓ | ✓ |
| Plan workouts (future dates) | ✗ | ✓ |
| Workout library | Limited | Full |
| Peak analysis | Basic | Full |

**Note:** Free accounts can only plan workouts for today and tomorrow relative to TrainingPeaks' UTC-6 server timezone.

---

## Appendix B: Comparison with Other MCP Servers

| Aspect | garth-mcp | todoist-mcp | This PRD |
|--------|-----------|-------------|----------|
| Auth method | OAuth tokens | API key | Session cookie |
| Token consumption | 66,000+ | ~5,000 | <2,000 |
| Tool count | 30+ | 12 | 5-8 |
| Transport | stdio | stdio | stdio |
| Credential storage | File + env | Env only | Keyring + encrypted file |

---

## Appendix C: Example Tool Responses

### tp_get_workouts response
```json
{
  "workouts": [
    {
      "id": "abc123",
      "date": "2025-01-08",
      "title": "Threshold Intervals",
      "type": "planned",
      "sport": "bike",
      "duration_planned": 90,
      "duration_actual": null,
      "tss": 85,
      "description": "4x8min at threshold"
    }
  ],
  "count": 1,
  "date_range": {
    "start": "2025-01-08",
    "end": "2025-01-08"
  }
}
```

### tp_get_peaks response
```json
{
  "peaks": [
    { "duration": "5s", "value": 1050, "date": "2024-12-15", "activity_id": "xyz789" },
    { "duration": "1m", "value": 420, "date": "2024-11-20", "activity_id": "xyz456" },
    { "duration": "5m", "value": 350, "date": "2024-12-01", "activity_id": "xyz123" },
    { "duration": "20m", "value": 310, "date": "2024-10-15", "activity_id": "xyz999" }
  ],
  "sport": "bike",
  "peak_type": "power",
  "days": 90
}
```

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-01-08 | Initial draft |
| 1.1 | 2025-01-08 | Added Claude Code implementation guide with sub-agent strategy, task breakdown, and compaction recovery |

---

## Appendix D: Initial PROGRESS.md Template

Create this file as the first action when starting the project:

```markdown
# TrainingPeaks MCP Server - Progress

## Current Phase
MVP

## Last Completed Task
None - Project starting

## Next Task  
SETUP-01 - Project scaffolding

## Blockers
None

## Completed Tasks

### Setup
- [ ] SETUP-01 - Project scaffolding

### Authentication (MVP)
- [ ] AUTH-01 - Keyring credential storage
- [ ] AUTH-02 - Cookie validation  
- [ ] AUTH-03 - CLI auth command
- [ ] AUTH-04 - Encrypted file fallback

### API Client (MVP)
- [ ] API-01 - HTTP client wrapper
- [ ] API-02 - Response parsing models

### Tools (MVP)
- [ ] TOOL-01 - tp_auth_status
- [ ] TOOL-02 - tp_get_profile
- [ ] TOOL-03 - tp_get_workouts
- [ ] TOOL-04 - tp_get_workout
- [ ] TOOL-05 - tp_get_peaks

### Server (MVP)
- [ ] SERVER-01 - MCP server setup

### Testing & Docs (MVP)
- [ ] TEST-01 - Integration test suite
- [ ] DOCS-01 - README and examples

### Tools (V1)
- [ ] TOOL-06 - tp_create_workout
- [ ] TOOL-07 - tp_move_workout
- [ ] TOOL-08 - tp_schedule_workout

### Platform & Security (V1)
- [ ] PLATFORM-01 - Windows support
- [ ] SECURITY-01 - Security audit
- [ ] TEST-02 - E2E test suite

## Architecture Decisions
(Record decisions here as they're made)

## API Endpoint Discoveries
(Document actual endpoints found via network analysis)

## Known Issues
(Track issues and workarounds)

## Session Notes
(Brief notes that help resume after compaction)
```

---

## Appendix E: Compaction Recovery Checklist

When Claude Code resumes after context compaction:

```
□ Read PROGRESS.md - understand current state
□ Read this PRD - refresh on requirements  
□ Check git status - any uncommitted work?
□ Check git log --oneline -10 - recent changes
□ Identify next task from PROGRESS.md
□ Read relevant source files for that task
□ Continue implementation
□ Update PROGRESS.md when task complete
□ Commit with [TASK-ID] prefix
```
