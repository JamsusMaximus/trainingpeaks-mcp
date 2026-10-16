#!/bin/bash
# One-click macOS installer for the TrainingPeaks MCP connector (read-only).
#
# Double-click this file in Finder. It:
#   1. finds Python 3.10+ (or downloads Apple-notarised Python from python.org
#      and opens its installer: you click Continue / Agree / Install and type
#      your Mac password);
#   2. downloads the connector at a fixed release tag into
#      ~/claude-tools/trainingpeaks-mcp (no git or Xcode tools needed);
#   3. creates its Python environment and installs it with browser support;
#   4. installs any tp-mcp plugin wheel (*.whl) placed beside this script;
#   5. adds the "trainingpeaks" server, locked read-only, to Claude Desktop's
#      config, keeping every other server and setting;
#   6. signs in to TrainingPeaks from Chrome (Keychain prompt: type your Mac
#      password, click Always Allow);
#   7. restarts Claude Desktop.
# Everything is logged to ~/claude-tools/install-<date>.log.
#
# Safe to run again: it updates in place. An existing install is moved aside
# (~/claude-tools/trainingpeaks-mcp.old-<date>), never deleted. Your
# TrainingPeaks credential and ~/.tp-mcp data are not touched.
#
# Overrides (for testing and maintainers; a coach never needs these):
#   TP_MCP_TAG=<tag>           release tag to install (default below)
#   TP_MCP_TARBALL=<file>      install from a local .tar.gz instead of GitHub
#   TP_INSTALL_SKIP_AUTH=1     skip the TrainingPeaks sign-in step
#   TP_INSTALL_SKIP_APP=1      do not quit / reopen Claude Desktop
#   TP_INSTALL_NO_PAUSE=1      do not wait for key presses
#   TP_INSTALL_NO_PYTHON_DOWNLOAD=1  never download Python; fail instead

set -Eeuo pipefail

TAG="${TP_MCP_TAG:-v3.2.1-ro1}"
REPO_TARBALL_URL="https://github.com/lukehardiman/trainingpeaks-mcp/archive/refs/tags/${TAG}.tar.gz"
PY_VERSION="3.13.16"
PY_PKG_URL="https://www.python.org/ftp/python/${PY_VERSION}/python-${PY_VERSION}-macos11.pkg"
PY_PKG_SHA256="30666509020b4da0dd8bc2e773255f34d76b7bb80b66960a928d5f6daa0192d7"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOLS_DIR="$HOME/claude-tools"
INSTALL_DIR="$TOOLS_DIR/trainingpeaks-mcp"
CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$TOOLS_DIR"
LOG="$TOOLS_DIR/install-$STAMP.log"
: > "$LOG"

pause() {
    if [ -z "${TP_INSTALL_NO_PAUSE:-}" ]; then
        read -n 1 -s -r -p "$1" || true
        echo
    fi
}

say() { echo "$*" | tee -a "$LOG"; }

# Run a command with its output going to the log only.
quiet() { "$@" >>"$LOG" 2>&1; }

STEP="starting"
finish_fail() {
    trap - ERR
    echo >>"$LOG"
    echo "FAILED during: $STEP" >>"$LOG"
    echo
    echo "============================================================"
    echo "FAILURE: the install stopped while $STEP."
    echo "Nothing was sent anywhere. Please send this file to your"
    echo "technical support person:"
    echo "    $LOG"
    echo "============================================================"
    pause "Press any key to close this window."
    exit 1
}
trap finish_fail ERR

say "TrainingPeaks connector installer ($TAG) - $(date)"
say "macOS $(sw_vers -productVersion 2>/dev/null || echo unknown), $(uname -m)"
say ""

# ---------------------------------------------------------------- 1. Python
STEP="looking for Python 3.10 or newer"

py_ok() {
    "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1
}

find_python() {
    local c
    # python.org installs first (newest version first), then Homebrew.
    for c in $(ls -d /Library/Frameworks/Python.framework/Versions/3.* 2>/dev/null | sort -t. -k3 -n -r); do
        if [ -x "$c/bin/python3" ] && py_ok "$c/bin/python3"; then
            echo "$c/bin/python3"; return 0
        fi
    done
    for c in /usr/local/bin/python3 /opt/homebrew/bin/python3; do
        if [ -x "$c" ] && py_ok "$c"; then echo "$c"; return 0; fi
    done
    # /usr/bin/python3 is only a stub that pops up Apple's "install developer
    # tools" dialog unless those tools are already installed, so ask first.
    if xcode-select -p >/dev/null 2>&1 && py_ok /usr/bin/python3; then
        echo /usr/bin/python3; return 0
    fi
    return 1
}

install_python() {
    if [ -n "${TP_INSTALL_NO_PYTHON_DOWNLOAD:-}" ]; then
        return 1
    fi
    local pkg="$TOOLS_DIR/python-$PY_VERSION-macos11.pkg"
    say "Python 3.10 or newer is not installed. Downloading Python $PY_VERSION from python.org..."
    if ! curl -fL --retry 2 -o "$pkg" "$PY_PKG_URL" >>"$LOG" 2>&1; then
        return 1
    fi
    local got
    got="$(shasum -a 256 "$pkg" | awk '{print $1}')"
    if [ "$got" != "$PY_PKG_SHA256" ]; then
        say "The Python download did not match its expected checksum; not opening it."
        rm -f "$pkg"
        return 1
    fi
    quiet pkgutil --check-signature "$pkg" || { rm -f "$pkg"; return 1; }
    echo
    echo "------------------------------------------------------------"
    echo "The Python installer is opening now. In its window:"
    echo "  click Continue, Continue, Continue, Agree, then Install,"
    echo "  type your Mac password when asked, and click Close at the end."
    echo "This window carries on by itself once the installer closes."
    echo "------------------------------------------------------------"
    open -W "$pkg"
    rm -f "$pkg"
    return 0
}

if ! PY="$(find_python)"; then
    if install_python && PY="$(find_python)"; then
        :
    else
        say ""
        say "Python could not be installed automatically. Opening the python.org download page."
        say "Download the macOS installer, double-click it, click Continue / Agree / Install,"
        say "then double-click this installer again."
        open "https://www.python.org/downloads/macos/" || true
        STEP="installing Python (download it from python.org, then run this installer again)"
        finish_fail
    fi
fi
say "Python: $PY ($("$PY" --version 2>&1))"

# ---------------------------------------------------------------- 2. Connector source
STEP="downloading the connector ($TAG)"
WORK="$(mktemp -d "$TOOLS_DIR/.download-XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

if [ -n "${TP_MCP_TARBALL:-}" ]; then
    say "Using local source: $TP_MCP_TARBALL"
    cp "$TP_MCP_TARBALL" "$WORK/src.tar.gz"
else
    say "Downloading the connector ($TAG)..."
    curl -fL --retry 2 -o "$WORK/src.tar.gz" "$REPO_TARBALL_URL" >>"$LOG" 2>&1
fi
mkdir "$WORK/src"
tar -xzf "$WORK/src.tar.gz" -C "$WORK/src" --strip-components 1
[ -f "$WORK/src/pyproject.toml" ] || { say "The download does not look like the connector."; false; }

STEP="putting the connector in place"
if [ -e "$INSTALL_DIR" ]; then
    OLD="$INSTALL_DIR.old-$STAMP"
    say "Moving the previous install aside to $OLD"
    mv "$INSTALL_DIR" "$OLD"
fi
mv "$WORK/src" "$INSTALL_DIR"

# ---------------------------------------------------------------- 3. Environment
STEP="creating the connector's Python environment"
say "Creating the Python environment..."
quiet "$PY" -m venv "$INSTALL_DIR/.venv"
VPY="$INSTALL_DIR/.venv/bin/python"
TPMCP="$INSTALL_DIR/.venv/bin/tp-mcp"

STEP="installing the connector (this needs the internet and takes a minute or two)"
say "Installing the connector (a minute or two)..."
quiet "$VPY" -m pip install --upgrade pip
(cd "$INSTALL_DIR" && quiet "$VPY" -m pip install -e ".[browser]")
[ -x "$TPMCP" ]

# ---------------------------------------------------------------- 4. Plugin wheels
STEP="installing the plugin file beside the installer"
WHEEL="$(ls -t "$SCRIPT_DIR"/*.whl 2>/dev/null | head -n 1 || true)"
if [ -n "$WHEEL" ]; then
    say "Installing plugin: $(basename "$WHEEL")"
    quiet "$VPY" -m pip install --force-reinstall --no-deps "$WHEEL"
    quiet "$VPY" -m pip install "$WHEEL"
else
    say "No plugin file beside the installer; skipping."
fi

STEP="checking the installed connector"
TOOL_COUNT="$("$VPY" -c 'import tp_mcp.server as s; print(len(s.TOOLS))' 2>>"$LOG")"
say "Connector ready: $TOOL_COUNT tools."

# ---------------------------------------------------------------- 5. Claude Desktop config
STEP="adding the connector to Claude Desktop's settings"
MERGE="$INSTALL_DIR/scripts/_merge_desktop_config.py"
RC=0
RESULT="$(trap - ERR; "$VPY" "$MERGE" add "$CONFIG" "$TPMCP" 2>>"$LOG")" || RC=$?
if [ $RC -eq 2 ]; then
    say "Claude Desktop's settings file is not valid JSON, so it was left untouched:"
    say "    $CONFIG"
    STEP="reading Claude Desktop's settings file (it is damaged; it was not changed)"
    finish_fail
elif [ $RC -ne 0 ]; then
    false
fi
say "Claude Desktop settings: $RESULT (read-only lock on)."

# ---------------------------------------------------------------- 6. TrainingPeaks sign-in
AUTH_NOTE=""
if [ -z "${TP_INSTALL_SKIP_AUTH:-}" ]; then
    STEP="signing in to TrainingPeaks"
    echo
    echo "------------------------------------------------------------"
    echo "Next: sign in to TrainingPeaks."
    echo "Make sure Google Chrome is open and logged into"
    echo "app.trainingpeaks.com with your COACH account."
    echo
    echo "A Keychain window will ask about \"Chrome Safe Storage\"."
    echo "Type your Mac login password and click  Always Allow."
    echo "------------------------------------------------------------"
    pause "Chrome logged in? Press any key to continue."
    RC=0
    AUTH_OUT="$(trap - ERR; "$TPMCP" auth --from-browser chrome 2>&1)" || RC=$?
    echo "$AUTH_OUT" >>"$LOG"
    if [ $RC -ne 0 ]; then
        say "$AUTH_OUT"
        STEP="signing in to TrainingPeaks (log into app.trainingpeaks.com in Chrome, then run this installer again)"
        finish_fail
    fi
    EMAIL="$(echo "$AUTH_OUT" | sed -n 's/.*Email: *//p' | tail -n 1)"
    [ -z "$EMAIL" ] && EMAIL="$(echo "$AUTH_OUT" | sed -n 's/.*authenticated as: *//p' | tail -n 1)"
    echo
    echo "############################################################"
    echo "  Signed in to TrainingPeaks as:  ${EMAIL:-unknown}"
    echo "  This must be your COACH account. If it is not, log into"
    echo "  the right account in Chrome and run this installer again."
    echo "############################################################"
    echo "Signed in as: ${EMAIL:-unknown}" >>"$LOG"
    AUTH_NOTE=" Signed in as ${EMAIL:-unknown}."
else
    say "TrainingPeaks sign-in skipped (TP_INSTALL_SKIP_AUTH)."
fi

# ---------------------------------------------------------------- 7. Restart Claude Desktop
if [ -z "${TP_INSTALL_SKIP_APP:-}" ]; then
    STEP="restarting Claude Desktop"
    if [ -d /Applications/Claude.app ] || [ -d "$HOME/Applications/Claude.app" ]; then
        say "Restarting Claude Desktop..."
        osascript -e 'tell application "Claude" to quit' >>"$LOG" 2>&1 || true
        sleep 3
        open -a Claude >>"$LOG" 2>&1 || true
    else
        say "Claude Desktop is not installed yet. Install it from claude.ai/download; it will pick up the connector."
    fi
fi

trap - ERR
echo
echo "============================================================"
echo "SUCCESS: the TrainingPeaks connector is installed.${AUTH_NOTE}"
echo "Open a NEW chat in Claude Desktop and ask: \"Run tp_auth_status\"."
echo "============================================================"
echo "SUCCESS" >>"$LOG"
pause "Press any key to close this window."
