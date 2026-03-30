# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TrainingPeaks MCP Server — a Python MCP server enabling AI assistants to interact with TrainingPeaks via 52+ tools. Uses browser cookie authentication (no official API key required).

## Commands

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,browser]"

# Run server
tp-mcp serve

# Authentication
tp-mcp auth --from-browser auto   # Extract from browser
tp-mcp auth-status

# Lint & type check
ruff check src/
mypy src/

# Tests
pytest tests/ -v
pytest tests/test_tools/test_workouts.py::test_name -v   # Single test
```

## Architecture

Layered design: **MCP Server → Tools → HTTP Client → Auth**

```
src/tp_mcp/
├── server.py          # Tool registration, MCP stdio transport
├── cli.py             # CLI entrypoint (auth, serve, config commands)
├── client/
│   ├── http.py        # TPClient: async httpx, token refresh, rate limiting
│   └── models.py      # Pydantic response models
├── auth/
│   ├── storage.py     # Credential hierarchy: env var → keyring → encrypted file
│   ├── keyring.py     # OS keyring integration
│   ├── encrypted.py   # AES-256-GCM fallback storage
│   ├── browser.py     # Cookie extraction from Chrome/Firefox/Safari/Edge
│   └── validator.py   # Cookie validation via API
└── tools/
    ├── _validation.py  # Shared Pydantic input validators
    ├── workouts.py     # CRUD + comments, copy, reorder
    ├── structure.py    # LLM-friendly step format → TP wire format, IF/TSS calc
    ├── analyze.py      # Time-series, zones, laps, power/pace distribution
    ├── events.py       # Calendar events, races, availability, notes
    ├── settings.py     # FTP, HR/speed zones, nutrition
    ├── metrics.py      # Weight, HRV, sleep, steps, SpO2, etc.
    ├── equipment.py    # Bikes, shoes
    ├── library.py      # Workout templates
    ├── fitness.py      # CTL/ATL/TSB trends
    ├── peaks.py        # Power/running PRs
    └── ...             # weekly_summary, atp, profile, auth_status, etc.
```

## Tool Pattern

Every tool follows this structure:
```python
async def tp_<action>(param: str) -> dict[str, Any]:
    try:
        params = SomeInput(param=param)
    except ValidationError as e:
        return {"isError": True, "error_code": "VALIDATION_ERROR", "message": format_validation_error(e)}

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {"isError": True, "error_code": "AUTH_INVALID", "message": "..."}

        response = await client.get(f"/endpoint/{athlete_id}")
        if response.is_error:
            return {"isError": True, "error_code": response.error_code.value, "message": response.message}

        return {"success": True, "data": response.data}
```

## Key Details

**HTTP Client (`client/http.py`):**
- Base URL: `https://tpapi.trainingpeaks.com`
- Exchanges session cookie for OAuth token at `/users/v3/token`; tokens cached in memory, refreshed 60s before expiry
- Rate limit: 150ms minimum between requests
- Timeout: 30s

**Sport type IDs** are hardcoded in `tools/workouts.py` as `SPORT_TYPE_MAP` — not queryable from the API. Values are `(sportTypeId, subSportTypeId)` tuples.

**Workout structure format** (`tools/structure.py`): Tools accept a simplified step-based JSON format that `structure.py` converts to the TP wire format, computing IF/TSS automatically.

**Auth security:** Tool results are scrubbed for credential-related keys before returning to Claude. Credentials never appear in tool output.

**Input validation:** All tools use Pydantic models from `tools/_validation.py`. Date ranges max out at 90 days. Use `format_validation_error()` for user-friendly messages.

## Configuration

- `pyproject.toml`: build (hatchling), deps, ruff (line-length=120), mypy, pytest (`asyncio_mode = "auto"`)
- CI: `.github/workflows/ci.yml` — runs ruff, mypy, pytest on Python 3.10–3.14
