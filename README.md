# TrainingPeaks MCP Server

Connect TrainingPeaks to Claude and other AI assistants via the Model Context Protocol (MCP). Query your workouts, analyze training load, compare power data, and track fitness trends through natural conversation.

## What You Can Do

Ask your AI assistant questions like:
- "What workouts did I do last week?"
- "Compare my 20-minute power from this year vs last year"
- "How is my fitness trending? Am I ready to race?"
- "Show me the PRs I set in yesterday's ride"

## Features

| Tool | Description |
|------|-------------|
| `tp_get_workouts` | Query workouts by date range (planned and completed) |
| `tp_get_workout` | Get detailed metrics for a single workout |
| `tp_get_peaks` | Compare power PRs (5sec to 90min) and running PRs (400m to marathon) |
| `tp_get_fitness` | Track CTL, ATL, and TSB (fitness, fatigue, form) |
| `tp_get_workout_prs` | See personal records set in a specific session |

## Quick Start

```bash
# Clone and install
git clone https://github.com/JamsusMaximus/trainingpeaks-mcp.git
cd trainingpeaks-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Authenticate (one-time setup)
tp-mcp auth
```

## Authentication

TrainingPeaks doesn't have a public API. This server uses session cookie authentication (same approach as tp2intervals and similar tools).

### Getting Your Cookie

1. Log into [TrainingPeaks](https://www.trainingpeaks.com)
2. Open DevTools (`Cmd+Option+I` on Mac, `F12` on Windows)
3. Go to **Application** → **Cookies** → `trainingpeaks.com`
4. Copy the value of `Production_tpAuth`

### Store It

```bash
tp-mcp auth        # Paste cookie, validates and stores securely
tp-mcp auth-status # Check if authenticated
tp-mcp auth-clear  # Remove stored credentials
```

Credentials are stored in your system keyring (macOS Keychain, Windows Credential Locker, Linux Secret Service).

## Claude Desktop Setup

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "trainingpeaks": {
      "command": "/path/to/trainingpeaks-mcp/.venv/bin/tp-mcp",
      "args": ["serve"]
    }
  }
}
```

Restart Claude Desktop. The TrainingPeaks tools will be available immediately.

## Tool Reference

### tp_get_workouts
List workouts in a date range. Max 90 days per query.

```json
{ "start_date": "2026-01-01", "end_date": "2026-01-07", "type": "completed" }
```

### tp_get_workout
Get full details for one workout including power, HR, cadence, TSS.

```json
{ "workout_id": "123456789" }
```

### tp_get_peaks
Get ranked personal records. Bike: power metrics. Run: pace/speed metrics.

```json
{ "sport": "Bike", "pr_type": "power20min", "days": 365 }
```

**Bike types:** `power5sec`, `power1min`, `power5min`, `power10min`, `power20min`, `power60min`, `power90min`

**Run types:** `speed400Meter`, `speed1K`, `speed5K`, `speed10K`, `speedHalfMarathon`, `speedMarathon`

### tp_get_fitness
Get training load metrics over time.

```json
{ "days": 90 }
```

Returns daily CTL (chronic training load / fitness), ATL (acute training load / fatigue), and TSB (training stress balance / form).

### tp_get_workout_prs
Get PRs set during a specific workout.

```json
{ "workout_id": "123456789" }
```

## What is MCP?

[Model Context Protocol](https://modelcontextprotocol.io) is an open standard for connecting AI assistants to external data sources. MCP servers expose tools that AI models can call to fetch real-time data, enabling assistants like Claude to access your TrainingPeaks account through natural language.

## Security

- Credentials stored in system keyring (not plaintext)
- Encrypted file fallback for headless environments
- No credentials in logs or error messages
- stdio transport only (no network exposure)
- Read-only access (no workout modifications)

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
mypy src/
ruff check src/
```

## Cookie Expiration

TrainingPeaks cookies last several weeks. When expired, tools will return auth errors. Run `tp-mcp auth` again with a fresh cookie.

## License

MIT
