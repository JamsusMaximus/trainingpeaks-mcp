# TrainingPeaks MCP Server

<a href="https://glama.ai/mcp/servers/@JamsusMaximus/TrainingPeaks-MCP">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@JamsusMaximus/TrainingPeaks-MCP/badge" alt="TrainingPeaks MCP server" />
</a>

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

#### Step 2: Get Your TrainingPeaks Cookie

TrainingPeaks doesn't have a public API, so we use session cookie authentication.

1. **Log into TrainingPeaks** at [trainingpeaks.com](https://www.trainingpeaks.com)

2. **Open browser DevTools**
   - Mac: `Cmd + Option + I`
   - Windows/Linux: `F12`

3. **Navigate to cookies**
   - Chrome/Edge: **Application** tab → **Cookies** → `https://www.trainingpeaks.com`
   - Firefox: **Storage** tab → **Cookies** → `https://www.trainingpeaks.com`
   - Safari: **Storage** tab → **Cookies** (enable DevTools in Preferences → Advanced first)

4. **Find and copy `Production_tpAuth`**
   - Look for a cookie named `Production_tpAuth`
   - Double-click the **Value** column to select it
   - Copy (`Cmd+C` / `Ctrl+C`)

#### Step 3: Store Your Cookie

```bash
tp-mcp auth
```

Paste your cookie when prompted. It will be validated and stored securely in your system keyring.

**Other auth commands:**
```bash
tp-mcp auth-status  # Check if authenticated
tp-mcp auth-clear   # Remove stored credentials
```

#### Step 4: Add to Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "trainingpeaks": {
      "command": "/full/path/to/trainingpeaks-mcp/.venv/bin/tp-mcp",
      "args": ["serve"]
    }
  }
}
```

> **Important:** Replace `/full/path/to/` with the actual path where you cloned the repo.

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

[Model Context Protocol](https://modelcontextprotocol.io) is an open standard for connecting AI assistants to external data sources. MCP servers expose tools that AI models can call to fetch real-time data, enabling assistants like Claude to access your TrainingPeaks account through natural language.

## Security

- Credentials stored in system keyring (not plaintext)
- Encrypted file fallback for headless environments
- No credentials in logs or error messages
- stdio transport only (no network exposure)
- Read-only access (no workout modifications)

## Cookie Expiration

TrainingPeaks cookies last several weeks. When expired, tools will return auth errors. Run `tp-mcp auth` again with a fresh cookie.

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
mypy src/
ruff check src/
```

## License

MIT
