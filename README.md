# TrainingPeaks MCP Server

<a href="https://glama.ai/mcp/servers/@JamsusMaximus/TrainingPeaks-MCP">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@JamsusMaximus/TrainingPeaks-MCP/badge" alt="TrainingPeaks MCP server" />
</a>

Connect TrainingPeaks to Claude and other AI assistants via the Model Context Protocol (MCP). Query your workouts, analyze training load, compare power data, and track fitness trends through natural conversation.

**No API approval required.** The official Training Peaks API is approval-gated, but this server uses secure cookie authentication that any user can set up in minutes. Your cookie is stored in your system keyring, never transmitted anywhere except to TrainingPeaks.

## What You Can Do

![Example conversation with Claude using TrainingPeaks MCP](docs/images/screenshot.png)

Ask your AI assistant questions like:
- "Compare my FTP progression this year vs last year"
- "What was my TSS ramp rate in the 6 weeks before my best 20-min power?"
- "Am I ready to race? Show my form trend and recent workout quality"
- "Which days of the week do I typically train hardest?"
- "Find weeks where I exceeded 800 TSS and show what happened to my form after"

## Features

| Tool | Description |
|------|-------------|
| `tp_get_workouts` | Query workouts by date range (planned and completed) |
| `tp_get_workout` | Get detailed metrics for a single workout |
| `tp_get_peaks` | Compare power PRs (5sec to 90min) and running PRs (400m to marathon) |
| `tp_get_fitness` | Track CTL, ATL, and TSB (fitness, fatigue, form) |
| `tp_get_workout_prs` | See personal records set in a specific session |

---

## Setup Options

### Option A: Auto-Setup with Claude Code

If you have [Claude Code](https://claude.ai/code), paste this prompt:

```
Set up the TrainingPeaks MCP server from https://github.com/JamsusMaximus/trainingpeaks-mcp - clone it, create a venv, install it, then walk me through getting my TrainingPeaks cookie from my browser and run tp-mcp auth. Finally, add it to my Claude Desktop config.
```

Claude will handle the installation and guide you through authentication step-by-step.

### Option B: Manual Setup

#### Step 1: Install

```bash
git clone https://github.com/JamsusMaximus/trainingpeaks-mcp.git
cd trainingpeaks-mcp
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

#### Step 2: Authenticate

**Option A: Auto-extract from browser (easiest)**

If you're logged into TrainingPeaks in your browser:

```bash
pip install tp-mcp[browser]  # One-time: install browser support
tp-mcp auth --from-browser chrome  # Or: firefox, safari, edge, auto
```

> **macOS note:** You may see security prompts for Keychain or Full Disk Access. This is normal - browser cookies are encrypted and require permission to read.

**Option B: Manual cookie entry**

1. Log into [app.trainingpeaks.com](https://app.trainingpeaks.com)
2. Open DevTools (`F12`) → **Application** tab → **Cookies**
3. Find `Production_tpAuth` and copy its value
4. Run `tp-mcp auth` and paste when prompted

**Other auth commands:**
```bash
tp-mcp auth-status  # Check if authenticated
tp-mcp auth-clear   # Remove stored cookie
```

#### Step 4: Add to Claude Desktop

Run this to get your config snippet:

```bash
tp-mcp config
```

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows) and paste it inside `mcpServers`. Example with multiple servers:

```json
{
  "mcpServers": {
    "some-other-server": {
      "command": "npx",
      "args": ["some-other-mcp"]
    },
    "trainingpeaks": {
      "command": "/Users/you/trainingpeaks-mcp/.venv/bin/tp-mcp",
      "args": ["serve"]
    }
  }
}
```

Restart Claude Desktop. You're ready to go!

---

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

[Model Context Protocol](https://modelcontextprotocol.io) is an open standard for connecting AI assistants to external data sources. MCP servers expose tools that AI models can call to fetch real-time data, enabling assistants like Claude to access your Training Peaks account through natural language.

## Security

- Cookie stored in system keyring (not plaintext)
- Encrypted file fallback for headless environments
- No cookie values in logs or error messages
- stdio transport only (no network exposure)
- Read-only access (no workout modifications)

## Cookie Expiration

Training Peaks session cookies last several weeks. When expired, tools will return auth errors. Run `tp-mcp auth` again with a fresh cookie from your browser.

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
mypy src/
ruff check src/
```

## License

MIT
