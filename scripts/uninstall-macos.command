#!/bin/bash
# One-click macOS uninstaller for the TrainingPeaks MCP connector.
#
# Double-click this file in Finder. It:
#   1. removes the "trainingpeaks" server from Claude Desktop's config
#      (a dated backup of the file is kept; other servers are untouched);
#   2. offers to clear the stored TrainingPeaks sign-in from the Keychain
#      (and the installer's note of which account it was);
#   3. moves ~/claude-tools/trainingpeaks-mcp (and any earlier installs the
#      installer moved aside, trainingpeaks-mcp.old-*) to the Trash;
#   4. asks before moving ~/.tp-mcp (downloaded data) to the Trash; the
#      default is to keep it.
# Everything is logged to ~/claude-tools/uninstall-<date>.log.
#
# Overrides (testing only):
#   TP_INSTALL_SKIP_APP=1   do not quit / reopen Claude Desktop
#   TP_INSTALL_NO_PAUSE=1   do not wait for key presses; answer "no" to questions
#   TP_UNINSTALL_ANSWERS=yn answers to the two questions (sign-in, data), e.g. "yn"

set -Eeuo pipefail

TOOLS_DIR="$HOME/claude-tools"
INSTALL_DIR="$TOOLS_DIR/trainingpeaks-mcp"
CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
DATA_DIR="$HOME/.tp-mcp"
TRASH="$HOME/.Trash"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$TOOLS_DIR"
LOG="$TOOLS_DIR/uninstall-$STAMP.log"
: > "$LOG"

ANSWERS="${TP_UNINSTALL_ANSWERS:-}"
pause() {
    if [ -z "${TP_INSTALL_NO_PAUSE:-}" ]; then
        read -n 1 -s -r -p "$1" || true
        echo
    fi
}
ask() {  # ask "<question>" -> 0 for yes
    local a
    if [ -n "$ANSWERS" ]; then
        a="${ANSWERS:0:1}"; ANSWERS="${ANSWERS:1}"
        echo "$1 [y/N] $a"
    elif [ -n "${TP_INSTALL_NO_PAUSE:-}" ]; then
        a="n"
    else
        read -r -p "$1 [y/N] " a || a="n"
    fi
    [ "$a" = "y" ] || [ "$a" = "Y" ]
}
say() { echo "$*" | tee -a "$LOG"; }

to_trash() {  # to_trash <path>: move into ~/.Trash under a unique name
    local name dest
    name="$(basename "$1")"
    dest="$TRASH/$name"
    [ -e "$dest" ] && dest="$TRASH/$name-$STAMP"
    mkdir -p "$TRASH"
    mv "$1" "$dest"
    say "Moved to the Trash: $1"
}

STEP="starting"
finish_fail() {
    trap - ERR
    echo "FAILED during: $STEP" >>"$LOG"
    echo
    echo "============================================================"
    echo "FAILURE: the uninstall stopped while $STEP."
    echo "Please send this file to your technical support person:"
    echo "    $LOG"
    echo "============================================================"
    pause "Press any key to close this window."
    exit 1
}
trap finish_fail ERR

say "TrainingPeaks connector uninstaller - $(date)"

# Find a Python to edit the config with: the connector's own, else any 3.10+.
VPY="$INSTALL_DIR/.venv/bin/python"
MERGE="$INSTALL_DIR/scripts/_merge_desktop_config.py"

# ---------------------------------------------------------------- 1. Config entry
STEP="removing the connector from Claude Desktop's settings"
if [ -f "$CONFIG" ]; then
    if [ -x "$VPY" ] && [ -f "$MERGE" ]; then
        RC=0
        RESULT="$(trap - ERR; "$VPY" "$MERGE" remove "$CONFIG" 2>>"$LOG")" || RC=$?
        if [ $RC -eq 2 ]; then
            say "Claude Desktop's settings file is not valid JSON; it was left untouched."
            finish_fail
        elif [ $RC -ne 0 ]; then
            false
        fi
        say "Claude Desktop settings: $RESULT."
    else
        say "The connector's files are missing, so its settings entry could not be removed"
        say "automatically. Remove \"trainingpeaks\" from: $CONFIG"
    fi
else
    say "No Claude Desktop settings file; nothing to remove."
fi

# ---------------------------------------------------------------- 2. Sign-in
STEP="clearing the TrainingPeaks sign-in"
if [ -x "$INSTALL_DIR/.venv/bin/tp-mcp" ]; then
    if ask "Also remove the stored TrainingPeaks sign-in from this Mac?"; then
        "$INSTALL_DIR/.venv/bin/tp-mcp" auth-clear 2>&1 | tee -a "$LOG"
        # The installer's note of which account was signed in (an email only).
        rm -f "$TOOLS_DIR/.trainingpeaks-account"
    else
        say "TrainingPeaks sign-in kept."
    fi
fi

# ---------------------------------------------------------------- 3. Connector files
STEP="moving the connector to the Trash"
if [ -e "$INSTALL_DIR" ]; then
    to_trash "$INSTALL_DIR"
else
    say "No connector folder at $INSTALL_DIR."
fi
# Earlier installs the installer moved aside rather than deleted.
for OLD in "$INSTALL_DIR".old-*; do
    [ -e "$OLD" ] && to_trash "$OLD"
done

# ---------------------------------------------------------------- 4. Data
STEP="handling downloaded data"
if [ -e "$DATA_DIR" ]; then
    if ask "Also move downloaded TrainingPeaks data ($DATA_DIR) to the Trash?"; then
        to_trash "$DATA_DIR"
    else
        say "Downloaded data kept at $DATA_DIR."
    fi
fi

# ---------------------------------------------------------------- 5. Restart
if [ -z "${TP_INSTALL_SKIP_APP:-}" ]; then
    if [ -d /Applications/Claude.app ] || [ -d "$HOME/Applications/Claude.app" ]; then
        STEP="restarting Claude Desktop"
        osascript -e 'tell application "Claude" to quit' >>"$LOG" 2>&1 || true
        sleep 3
        open -a Claude >>"$LOG" 2>&1 || true
    fi
fi

trap - ERR
echo
echo "============================================================"
echo "SUCCESS: the TrainingPeaks connector has been removed."
echo "============================================================"
echo "SUCCESS" >>"$LOG"
pause "Press any key to close this window."
