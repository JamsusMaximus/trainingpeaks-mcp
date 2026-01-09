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
2. Open DevTools (F12) → Network tab
3. Navigate to any page on trainingpeaks.com
4. Find a request to `tpapi.trainingpeaks.com`
5. In the request headers, find the `Cookie` header
6. Copy the value of the `Production_tpAuth` cookie

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

### tp_get_peaks
Get power or pace peak data.

Parameters:
- `peak_type`: "power" or "pace"
- `sport`: "bike" or "run"
- `duration`: "5s", "1m", "5m", "20m", "60m", or "all" (default: "all")
- `days`: Days of history, 1-365 (default: 90)

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
