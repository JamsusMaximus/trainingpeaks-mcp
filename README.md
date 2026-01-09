# TrainingPeaks MCP Server

MCP server for TrainingPeaks integration with AI assistants like Claude Desktop.

## Features

- **Read-only access** to your TrainingPeaks data (MVP)
- Query workouts for any date range
- Get detailed workout information
- Access power and pace peak data
- Secure credential storage (system keyring or encrypted file)

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd trainingpeaks-mcp

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install
pip install -e .
```

## Authentication

TrainingPeaks doesn't offer a public API. This server uses session cookie authentication (the same approach used by tools like tp2intervals).

### Getting Your Cookie

1. Log into [TrainingPeaks](https://www.trainingpeaks.com) in your browser
2. Open DevTools:
   - **Chrome/Edge:** `Cmd+Option+I` (Mac) or `F12` (Windows)
   - **Safari:** `Cmd+Option+I` (enable in Preferences → Advanced → Show Developer menu first)
3. Click the **Application** tab (Chrome/Edge) or **Storage** tab (Safari)
4. In the left sidebar, expand **Cookies** → click `https://www.trainingpeaks.com`
5. Find the cookie named `Production_tpAuth` in the list
6. Double-click the **Value** to select it, then copy (`Cmd+C`)

### Storing Your Cookie

```bash
tp-mcp auth
```

Follow the prompts to paste your cookie. It will be validated against TrainingPeaks and stored securely in your system keyring.

### Checking Auth Status

```bash
tp-mcp auth-status
```

### Clearing Credentials

```bash
tp-mcp auth-clear
```

## Usage with Claude Desktop

Add to your Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "trainingpeaks": {
      "command": "/path/to/.venv/bin/tp-mcp",
      "args": ["serve"]
    }
  }
}
```

Replace `/path/to/.venv/bin/tp-mcp` with the actual path to the `tp-mcp` command in your virtual environment.

## Available Tools

### tp_auth_status
Check authentication status. Use when other tools return auth errors.

### tp_get_profile
Get athlete profile and ID.

### tp_get_workouts
Get workouts for date range. Returns planned and completed.

Parameters:
- `start_date`: Start date (YYYY-MM-DD)
- `end_date`: End date (YYYY-MM-DD)
- `type`: Filter - "all", "planned", or "completed" (default: "all")

### tp_get_workout
Get full workout details including structure.

Parameters:
- `workout_id`: Workout ID

### tp_get_workout_prs
Get personal records set during a specific workout.

Parameters:
- `workout_id`: Workout ID to get PRs for

Returns power, heart rate, and speed records set during that workout.

### tp_get_peaks
Get ranked personal records by sport and type.

Parameters:
- `sport`: "Bike" or "Run"
- `pr_type`: PR type (see below)
- `days`: Days of history (default: 365)

**Bike PR types:** power5sec, power1min, power5min, power10min, power20min, power60min, power90min, hR5sec, hR1min, hR5min, hR10min, hR20min, hR60min, hR90min

**Run PR types:** speed400Meter, speed800Meter, speed1K, speed1Mi, speed5K, speed5Mi, speed10K, speed10Mi, speedHalfMarathon, speedMarathon, speed50K, plus HR types

### tp_get_fitness
Get CTL/ATL/TSB fitness and fatigue data.

Parameters:
- `days`: Days of history (default: 90)

Returns daily fitness metrics (CTL=fitness, ATL=fatigue, TSB=form) with status.

## Security

- Credentials are stored in your system keyring (macOS Keychain, Windows Credential Locker, Linux Secret Service)
- Fallback to encrypted file storage (`~/.config/trainingpeaks-mcp/credentials.enc`) for headless environments
- Credentials are never logged or included in error messages
- 401 responses automatically clear stored credentials
- Server uses stdio transport only (no network exposure)

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Type checking
mypy src/

# Linting
ruff check src/
```

## Project Status

See [PROGRESS.md](PROGRESS.md) for current implementation status.

## Cookie Expiration

TrainingPeaks session cookies typically last several weeks but will eventually expire. When they do, you'll see auth errors from the tools. Simply run `tp-mcp auth` again to re-authenticate with a fresh cookie.

## License

MIT
