# Installer "silent exit" after the macOS line — 2026-10-17

**Reported:** double-clicking `scripts/install-macos.command` (Girona bundle copy) on Luke's Mac
(macOS 15.5, arm64) showed the header, `macOS 15.5, arm64`, then
`Press any key to close this window.` and nothing else.

## Finding

The script had **not** ended. It was paused inside a failure handler that was running in a
subshell, and the failure banner had been captured as program output instead of being shown.

Line numbers below are from the **original** file (before this fix).

1. `set -Eeuo pipefail` (line 41). The `-E` (errtrace) makes subshells inherit the
   `ERR` trap, including `$(...)` command substitutions. `trap finish_fail ERR` is line 86.
2. The first thing that runs after the macOS line (89–90) is `find_python`, called as
   `PY="$(find_python)"` (line 151). Inside it, line 106:
   ```bash
   for c in $(ls -d /Library/Frameworks/Python.framework/Versions/3.* 2>/dev/null | sort -t. -k3 -n -r); do
   ```
   Luke's Mac has no python.org framework Python (only Homebrew `/opt/homebrew/bin/python3`),
   so `ls` exits 1. Because of `pipefail`, the whole pipeline fails, and the inherited ERR trap
   fires **inside that nested `$(...)`**.
3. `finish_fail` (72–85) runs in that subshell:
   - Its `echo` banner (`FAILURE: the install stopped while looking for Python…`) goes to
     stdout, and stdout there **is the command substitution**. The banner becomes the `for`
     loop's word list, so it is never shown.
   - `pause` (61) uses `read -p`, and bash writes that prompt to **stderr**, which the Terminal
     shows. That is the only line the coach sees: `Press any key to close this window.`
   - The log gets a false `FAILED during: looking for Python 3.10 or newer`.
4. After a key press, the subshell exits 1, the `for` loop iterates over the captured banner
   words (none is a Python), Homebrew Python is found, and the install **would have continued**
   (`Python: /opt/homebrew/bin/python3 …`). "Nothing else / no install" means the window was
   closed (or the key press was not given) at that prompt. The prompt said "close this window",
   so closing it was the reasonable thing to do.

**Why the other suspects don't apply:**
- No "already installed" short-circuit exists. The script always reinstalls.
- A failing command under `set -e` whose stderr is swallowed would still show the
  FAILURE banner from the top-level trap. It is silent only when the trap runs inside `$(...)`.

**Who hits it:** any Mac **without** a python.org Python in `/Library/Frameworks`. That covers
every coach who has Homebrew Python, `/usr/bin/python3` (CLT), or no Python. A coach who has
no Python at all would see the prompt, press a key, and then get the download. A coach who closes
the window gets nothing.

### Reproduced (read-only, sandboxed HOME; installer not run)
I ran lines 1–164 (step 1 only) with `HOME` set to a scratch directory under a pseudo-terminal, using `/bin/bash` 3.2.57:
```
TrainingPeaks connector installer (v3.2.2-ro1) - Sat 17 Oct 2026 18:12:04 SAST
macOS 15.5, arm64

Press any key to close this window.Python: /opt/homebrew/bin/python3 (Python 3.14.5)
```
The log contained `FAILED during: looking for Python 3.10 or newer`.

### Other exit paths audited
| Path | Before | After |
|---|---|---|
| ERR trap inside `$(...)` (line 106; also 132, 168, 216 if they fail) | banner captured; only the prompt shows | subshell exits quietly. Line 106 is benign; 168/216 then fail in the main script, which shows the banner |
| `( cd … && pip install … )` (201) | banner from subshell, then exit | caught by new EXIT handler: "stopped unexpectedly while installing the connector…" |
| `set -u` unbound variable, or any exit the ERR trap misses | bash error line, no message, no pause | EXIT handler shows banner + log path + pause |
| Top-level failure (`finish_fail`) | banner | unchanged |
| Success / "installed, not signed in" | banner | unchanged |
| Window closed / Ctrl-C | — | nothing can be shown (expected) |

## Fix (applied to `scripts/install-macos.command`)
- `finish_fail` exits immediately with status 1 when `BASH_SUBSHELL > 0`, so it never prints into captured output or pauses in a subshell.
- New `on_exit` EXIT handler. It replaces the old `cleanup` trap and still removes `$WORK`. If no final message has been shown (`DONE` unset), it prints a FAILURE banner naming the step and the log file, then pauses. `DONE=1` is set by `finish_fail` and by the success/warn ending.
- Line 106 gets `|| true`, so "no python.org Python" is no longer treated as an error.

```diff
--- a/scripts/install-macos.command
+++ b/scripts/install-macos.command
@@ -69,8 +69,20 @@
 quiet() { "$@" >>"$LOG" 2>&1; }
 
 STEP="starting"
+DONE=""   # set once the final message (success or failure) has been shown
+WORK=""
+
 finish_fail() {
+    # set -E hands this trap to every $(...) and ( ... ) subshell. There its
+    # banner would be captured as the command's output (only the key-press
+    # prompt, on stderr, would show), and a failure there is either expected
+    # (e.g. ls finding no python.org Python) or reported again by the main
+    # script when the subshell's status comes back. So just leave the subshell.
+    if [ "${BASH_SUBSHELL:-0}" -gt 0 ]; then
+        exit 1
+    fi
     trap - ERR
+    DONE=1
     echo >>"$LOG"
     echo "FAILED during: $STEP" >>"$LOG"
     echo
@@ -84,6 +96,25 @@
     exit 1
 }
 trap finish_fail ERR
+
+# Any exit that did not show a final message (an error the ERR trap does not
+# see, such as an unset variable) still tells the coach what happened.
+on_exit() {
+    local rc=$?
+    if [ -n "$WORK" ]; then rm -rf "$WORK"; fi
+    if [ -z "$DONE" ] && [ "${BASH_SUBSHELL:-0}" -eq 0 ]; then
+        echo "STOPPED UNEXPECTEDLY (exit $rc) during: $STEP" >>"$LOG"
+        echo
+        echo "============================================================"
+        echo "FAILURE: the install stopped unexpectedly while $STEP."
+        echo "Nothing was sent anywhere. Please send this file to your"
+        echo "technical support person:"
+        echo "    $LOG"
+        echo "============================================================"
+        pause "Press any key to close this window."
+    fi
+}
+trap on_exit EXIT
 
 say "TrainingPeaks connector installer ($TAG) - $(date)"
 say "macOS $(sw_vers -productVersion 2>/dev/null || echo unknown), $(uname -m)"
@@ -103,7 +134,7 @@
         return 1
     fi
     # python.org installs first (newest version first), then Homebrew.
-    for c in $(ls -d /Library/Frameworks/Python.framework/Versions/3.* 2>/dev/null | sort -t. -k3 -n -r); do
+    for c in $(ls -d /Library/Frameworks/Python.framework/Versions/3.* 2>/dev/null | sort -t. -k3 -n -r || true); do
         if [ -x "$c/bin/python3" ] && py_ok "$c/bin/python3"; then
             echo "$c/bin/python3"; return 0
         fi
@@ -165,9 +196,7 @@
 
 # ---------------------------------------------------------------- 2. Connector source
 STEP="downloading the connector ($TAG)"
-WORK="$(mktemp -d "$TOOLS_DIR/.download-XXXXXX")"
-cleanup() { rm -rf "$WORK"; }
-trap cleanup EXIT
+WORK="$(mktemp -d "$TOOLS_DIR/.download-XXXXXX")"   # removed by on_exit
 
 if [ -n "${TP_MCP_TARBALL:-}" ]; then
     say "Using local source: $TP_MCP_TARBALL"
@@ -420,6 +449,7 @@
 fi
 
 trap - ERR
+DONE=1
 echo
 echo "============================================================"
 if [ -n "$END_WARN" ]; then
```

### Verified after the fix (pty, sandboxed HOME, `/bin/bash` 3.2)
- **Step 1 on this Mac:** prints `Python: /opt/homebrew/bin/python3 (Python 3.14.5)` with no prompt and no false FAILED line in the log.
- **Failing `$(...)` (TOOL_COUNT pattern):** shows one banner, `FAILURE: the install stopped while checking the installed connector.`, then the prompt.
- **Unset variable:** shows the bash error, then `FAILURE: the install stopped unexpectedly while …` and the prompt. The log line reports `exit 0`, because bash 3.2 does not pass the status through in this case. This is cosmetic and only affects the log.
- **Failing `( … )` subshell:** shows `FAILURE: the install stopped unexpectedly while …` and the prompt.
- `bash -n` passes.

## Quarantine (Q4)
- The script **never sets, reads or clears** `com.apple.quarantine`. No `xattr`, `spctl`, or Gatekeeper calls.
- **Nothing depends on running from a quarantined copy.** `SCRIPT_DIR` is only used to find `*.whl` beside the script. `.command` files are run by Terminal from their real path, with no App Translocation.
- The Python `.pkg` and the source tarball are fetched with `curl`, which does not set quarantine. Their integrity is checked by SHA-256 and `pkgutil --check-signature`, not by Gatekeeper.
- **The reverse does matter:** a coach's copy unzipped from a download *is* quarantined. On macOS 15, the first double-click is blocked, and the coach must use System Settings → Privacy & Security → "Open Anyway". Luke's local copy is not quarantined, so his test skips that step. To test what a coach sees, add the attribute as shown below.

## Lines for Luke to run
```bash
cd ~/Dev/trainingpeaks-mcp
bash -n scripts/install-macos.command && echo syntax-ok

# 1. Step-1 only, scratch HOME, real Terminal (should print "Python: …", no prompt):
mkdir -p /tmp/tpi-home && sed -n '1,/^say "Python: \$PY/p' scripts/install-macos.command > /tmp/tpi-step1.sh
echo 'DONE=1; echo "STEP 1 OK"' >> /tmp/tpi-step1.sh
HOME=/tmp/tpi-home TP_INSTALL_NO_PYTHON_DOWNLOAD=1 bash /tmp/tpi-step1.sh

# 2. Full run, real HOME but no sign-in and no app restart (moves the existing install aside as usual):
TP_INSTALL_SKIP_AUTH=1 TP_INSTALL_SKIP_APP=1 bash scripts/install-macos.command

# 3. Copy into the Girona bundle, then test the double-click as a coach sees it (quarantined):
xattr -w com.apple.quarantine "0081;$(printf %x $(date +%s));Safari;" /path/to/Girona/install-macos.command
#    double-click it in Finder; expect the Gatekeeper block, then "Open Anyway". Remove with:
xattr -d com.apple.quarantine /path/to/Girona/install-macos.command
```
Note: run 2 still uses `TAG` v3.2.2-ro1 from GitHub. Add `TP_MCP_TARBALL=<file>` to test against a local build.
