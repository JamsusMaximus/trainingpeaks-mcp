# Fork docs and installer follow-up: Phase 0 — 2026-10-18

Report only. Nothing in either repo or on the Desktop was edited. No git command that changes anything was run. Fork at `efa3a82` (tag `v3.2.2-ro1`), engine at `fe5aab6` (0.13.0).

Documents read:
- `~/Desktop/S2S/TP-CLAUDE-CONNECTOR-COACH-GUIDE.md` (the public coach guide; called "CG" below)
- `~/Dev/tp-analysis/GIRONA-ENGINE-INSTALL.md` (the Girona coach doc; "GE")
- `scripts/install-macos.command`
- `README.md` (the fork's installer and read-only sections)
- `~/Dev/tp-analysis/scripts/build_girona_zip.sh`

## Headline

1. **Two stale claims break things; the rest are wording.**
   - **The Terminal fallback pins `v3.2.1-ro1`** (CG A.2, and GE's "updates it in place to v3.2.1-ro1"). Engine 0.13.0 requires `tp-mcp>=3.2.2,<4`, and `tp-mcp` is not on PyPI. So the fallback followed by the Girona `.whl` fails with `No matching distribution found for tp-mcp`. Pin `v3.2.2-ro1`.
   - **GE says "four" engine tools in two places.** There are six. The troubleshooting line "the four tools do not appear" sends a coach looking for the wrong count.
2. **Four places tell a coach to ask by tool name:**
   - the installer's SUCCESS line;
   - CG 4.2, CG 4.3 and CG 7;
   - GE "If something is off".

   I propose plain words for each (item 2).
3. **The python.org branch works up to the installer window.** In a scratch HOME with every existing Python hidden, it:
   - downloaded the real `python-3.13.16-macos11.pkg`;
   - matched the pinned SHA-256;
   - passed `pkgutil --check-signature` (Developer ID Installer: Python Software Foundation, notarised).

   I stubbed only the GUI install (`open -W`). After that the script found the interpreter where the pkg puts it, installed v3.2.2-ro1 from GitHub, wrote the read-only config entry and ended **SUCCESS** (exit 0).

   The pkg itself confirms the stub's path. Every dependency has a binary wheel for CPython 3.13 on both arm64 and x86_64, so no compiler is needed.
4. **One related bug, outside the fork.** The Girona `Lap-Placement-On/Off.command` files run `/usr/bin/python3`. A Mac that needed the python.org download is a Mac without Apple's developer tools. On that Mac, `/usr/bin/python3` is only a stub: double-clicking either switch opens Apple's "install command line developer tools" dialog, and the switch does nothing. The fix belongs in `tp-analysis/scripts/build_girona_zip.sh` (row E1).

## 1. Stale claims and proposed edits

Current behaviour checked against:
- **Six engine tools:** `tp_analyze_week`, `tp_analyze_session`, `tp_get_trend`, `tp_render_week` (`mcp_tools.py`), and `tp_refresh_manifest`, `tp_review_manifest` (`manifest_tools.py`). The `tools()` entry point returns all six.
- **Refresh on first use:** `refresh_if_first_use` runs before the first `tp_analyze_week` / `tp_analyze_session` on an account with no overlay.
- **FTP:** FTP and % of FTP on every analysed verdict.
- **Lap switch:** the switch files ship in the Girona bundle only. Cape Town has only the two install scripts.
- **Installer:** default tag `v3.2.2-ro1`.

### Public coach guide (`~/Desktop/S2S/TP-CLAUDE-CONNECTOR-COACH-GUIDE.md`)

| # | Where | Says now | Why it's stale | Proposed edit |
|---|---|---|---|---|
| C1 | 3.1 (line 38) | "A folder appears with **Install-S2S-TrainingPeaks.command** inside (and, for some groups, a `.whl` file)." | Every bundle also has **Uninstall-S2S-TrainingPeaks.command** (section 5 depends on it). The Girona bundle also has **Lap-Placement-On.command** and **Lap-Placement-Off.command**. A coach told "Install… inside" who sees four files may think the zip is wrong. | "A folder appears with **Install-S2S-TrainingPeaks.command** and **Uninstall-S2S-TrainingPeaks.command** inside. Some groups' folders also hold a `.whl` file and two *Lap-Placement* files; your group's own instructions explain those." |
| C2 | 4.2 (line 94) | type: *"Run tp_auth_status"*. Claude should report authenticated, with your email. | This asks for the tool by name (item 2). | type: *"Am I signed in to TrainingPeaks? Which email?"* Claude should say you are signed in and give your coach email. |
| C3 | 4.3 (line 95) | *"Use tp_get_profile and tell me which TrainingPeaks account this is."* | This asks for the tool by name. | *"Which TrainingPeaks account are you connected to? Give me its name and account type."* (It checks the same thing as C2 by another route; alternatively, drop 4.3 and keep C2.) |
| C4 | 7 (line 120) | ask Claude *"Run tp_refresh_auth"* | This asks for the tool by name. | ask Claude *"Please refresh my TrainingPeaks sign-in from Chrome."* |
| C5 | Appendix A.2 (line 137) | `…/archive/refs/tags/v3.2.1-ro1.tar.gz` | The installer installs `v3.2.2-ro1`. Engine 0.13.0 needs ≥ 3.2.2: with 3.2.1, the `.whl` step in the same block fails. | `v3.2.2-ro1` |
| C6 | 3.3 (line 63) | Python installer: Continue → Continue → Continue → Agree → Install | **Not stale.** The pkg's `Distribution` shows Welcome, Read Me, License (Agree sheet) and then Install, with `rootVolumeOnly="true"`, so no destination page. | none |
| C7 | 3.4 (line 77) | SUCCESS … Continue to section 4. | Fine as it is. Once C2 lands, the installer's closing line and 4.2 should use the same question (item 2). | none beyond item 2 |

### Girona engine doc (`~/Dev/tp-analysis/GIRONA-ENGINE-INSTALL.md`)

| # | Where | Says now | Why it's stale | Proposed edit |
|---|---|---|---|---|
| G1 | line 4 | "together with **four** interval-analysis tools" | There are six. | "together with the interval-analysis tools (six: analyse a week, analyse a session, trends, the weekly report, and refreshing and reviewing your template list)" |
| G2 | line 10 | "updates it in place to **v3.2.1-ro1**" | The installer installs `v3.2.2-ro1`. | `v3.2.2-ro1` |
| G3 | §1 (lines 17–19) | "A folder appears with Install…, Uninstall… and a `tp_analysis-….whl` file." | The Girona bundle also has **Lap-Placement-On.command** and **Lap-Placement-Off.command**. | "…, Uninstall…, **Lap-Placement-On.command**, **Lap-Placement-Off.command** and a `tp_analysis-….whl` file." |
| G4 | §3 step 2 (lines 40–44) | The expected reply is a per-session verdict list with counts and per-interval numbers. | It doesn't say that (a) each analysed session now shows the day's FTP and every effort as % of FTP, or (b) the **first** analysis on the account reads the template libraries first and Claude then reads out questions. That is the first thing the coach will see, and it is slower. | Add: "Each analysed session shows the athlete's FTP for that day, with targets in watts and every effort as a % of it. The very first time you do this on your account it takes longer: the engine first reads your template libraries, and Claude then reads you a short list of questions about them (see "After you add templates"). You can answer them now or later." |
| G5 | "If something is off" (line 124) | "ask Claude to run `tp_refresh_auth`" | This asks for the tool by name. | "ask Claude to *refresh your TrainingPeaks sign-in from Chrome*, with Chrome logged into app.trainingpeaks.com." |
| G6 | line 127 | "The **four** tools do not appear in a new chat" | There are six. Also, "tools appear" means nothing to a coach. | "Claude says it has no interval-analysis tools in a new chat → …" (rest unchanged) |
| G7 | Lap-placement section | "double-click **Lap-Placement-On.command** from the install folder" | The wording is correct (the doc is Girona-only). The switch itself is broken on a Mac without developer tools (E1). | none in text; fix E1 |
| G8 | "After you add templates" | first analysis reads libraries; one question per template; calendar rows newest first | Current (updated in `fe5aab6`). | none |

### Fork README (`README.md`)

| # | Where | Says now | Why it's stale | Proposed edit |
|---|---|---|---|---|
| R1 | line 439 | allowlist "…`tp_render_*`, plus `tp_auth_status` and `tp_refresh_auth`" | Since `2c24adf`, `_READ_ONLY_EXTRA` also admits `tp_refresh_manifest` and `tp_review_manifest` by exact name (`server.py:1583`). | "…plus `tp_auth_status`, `tp_refresh_auth`, and, by exact name, `tp_refresh_manifest` and `tp_review_manifest` (the tp-analysis plugin's template-list tools: they read TrainingPeaks and write only a local file)." |
| R2 | line 212, maintainer overrides | lists six variables | `TP_INSTALL_PYTHON` (header line 34) is missing. | Add `TP_INSTALL_PYTHON` (use this Python 3.10+). |

### Bundle script (`~/Dev/tp-analysis/scripts/build_girona_zip.sh`): found by item 3

| # | Where | Problem | Proposed fix |
|---|---|---|---|
| E1 | line 49, generated `Lap-Placement-*.command` | The switch runs `/usr/bin/python3`. That runs Python only if Apple's developer tools are installed. On a Mac where the installer had to download Python, they are not: the double-click opens Apple's install-tools dialog and the switch is not set. | Run the connector's own interpreter, which the installer always creates: `PY="$HOME/claude-tools/trainingpeaks-mcp/.venv/bin/python"`. If it is missing, print "Run Install-S2S-TrainingPeaks.command first." and stop. Then use `"$PY" - <<'PY'`. The bundle test in `test_engine_polish.py` should assert the generated file contains no `/usr/bin/python3`. |

## 2. Installer closing line

Now (`install-macos.command:461`):
```
Open a NEW chat in Claude Desktop and ask: "Run tp_auth_status".
```
Proposed:
```
Open a NEW chat in Claude Desktop and ask: "Am I signed in to TrainingPeaks?"
```
Claude Desktop answers this with the auth-status tool by itself, so the coach never has to know the tool exists. CG 4.2 (C2) should use the same question, so the window and the guide match. No test pins this line. `tests/test_install_upgrade.py` checks only the `SUCCESS: …` text on the line before it.

## 3. python.org branch dry run

**Setup.** Everything was in the scratchpad, `…/scratchpad/pydry/` (not in the repo):

- **Environment.** `env -i`; `HOME` set to a scratch directory; `PATH=/usr/bin:/bin:/usr/sbin:/sbin`; `/bin/bash` 3.2. Sign-in, the Claude Desktop restart and key-press pauses were skipped (`TP_INSTALL_SKIP_AUTH=1`, `TP_INSTALL_SKIP_APP=1`, `TP_INSTALL_NO_PAUSE=1`). The Keychain and the real Claude config were never touched.
- **Why trimming PATH was not enough.** `find_python` checks fixed paths, not `PATH`: `/Library/Frameworks/…`, `/usr/local/bin/python3`, `/opt/homebrew/bin/python3`. So trimming `PATH` alone would still have found Homebrew. I ran a copy of the script with those three paths prefixed by an empty `$FAKEROOT`.
- **`/usr/bin/python3` was left as it is.** This Mac has developer tools, and its `/usr/bin/python3` is 3.9.6, which fails the 3.10 check. So that branch behaves exactly as it would on a Mac without the tools.
- **The one stub (stated as asked).** `open -W "$pkg"` was replaced by a function that:
  1. keeps a copy of the verified pkg;
  2. creates `$FAKEROOT/Library/Frameworks/Python.framework/Versions/3.13/bin/python3` as a symlink to Homebrew's 3.14.5.

  The real python.org Python cannot run from a moved location, because its binary links to `/Library/Frameworks/…` by absolute path. python.org Python was **not** installed on this Mac.

**Result (verbatim):**
```
Python 3.10 or newer is not installed. Downloading Python 3.13.16 from python.org...
------------------------------------------------------------
The Python installer is opening now. In its window: ...
------------------------------------------------------------
[stub] would run: open -W …/home/claude-tools/python-3.13.16-macos11.pkg
[stub] created …/fakeroot/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -> /opt/homebrew/bin/python3
Python: …/fakeroot/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 (Python 3.14.5)
Downloading the connector (v3.2.2-ro1)...
Creating the Python environment...
Installing the connector (a minute or two)...
No plugin file beside the installer; skipping.
Connector ready: 85 tools.
Claude Desktop settings: updated (read-only lock on).
TrainingPeaks sign-in skipped (TP_INSTALL_SKIP_AUTH).
SUCCESS: the TrainingPeaks connector is installed.
```
Exit 0. The scratch config holds exactly one `trainingpeaks` entry with `["serve", "--read-only"]`.

**What was real:**

| Check | Result |
|---|---|
| Download URL `…/3.13.16/python-3.13.16-macos11.pkg` | 200, 70,394,335 bytes |
| SHA-256 against `PY_PKG_SHA256` | match (the script would otherwise have said so and stopped) |
| `pkgutil --check-signature` | Developer ID Installer: Python Software Foundation (BMM5U3QVKW), notarised, timestamp 2026-09-30 |
| Where the pkg puts the interpreter | `Python_Framework.pkg` `install-location="/Library/Frameworks/Python.framework"`, and its payload holds `./Versions/3.13/bin/python3`. So it lands at `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3`, the path `find_python` checks first and the path the stub created. `Python_Command_Line_Tools.pkg` also adds `/usr/local/bin/python3`, the second path checked. |
| Installer panes | Welcome, Read Me, License and then Install, with no destination page (`rootVolumeOnly="true"`): the five clicks the script and CG 3.3 describe |
| Install with no compiler | `pip download --only-binary=:all:` for CPython 3.13 resolved every dependency (fork + `[browser]` + `fitdecode`) to wheels: 40 wheels on `macosx_11_0_arm64` and 40 on `macosx_10_13_x86_64`, none built from source |
| TLS under python.org Python | Not affected. python.org Python does not use the macOS certificate store until "Install Certificates.command" is run. But pip carries its own certificates, `httpx` uses `certifi`, `curl` is the system one, and `src/` has no `urllib.request` or default `ssl` context. |

**Not exercised (needs a real Mac without Python):**
- `open -W` waiting on the Installer.app GUI, and the password prompt.

  Reading the code: if the coach cancels, `find_python` still fails. The script then opens python.org/downloads and ends with a FAILURE banner that names the step, so the exit is not silent.
- The python.org installer's shell-profile step adds a `PATH` line to `~/.zprofile`. That is harmless, and the installer does not rely on it.

**Nothing in the fork's installer needs fixing for this branch.** The one defect found is E1, in the engine bundle.

## 4. Phase 1 plan (on approval)

**Fork (`~/Dev/trainingpeaks-mcp`):**
- `scripts/install-macos.command`: closing line (item 2).
- `README.md`: R1, R2.
- This report gains a short Phase 1 section.

**Desktop (not in a repo):** `~/Desktop/S2S/TP-CLAUDE-CONNECTOR-COACH-GUIDE.md`: C1–C5.

**Engine (`~/Dev/tp-analysis`), if you include it:**
- `GIRONA-ENGINE-INSTALL.md`: G1–G6.
- `scripts/build_girona_zip.sh`: E1, plus the test assertion.
- Rebuild both zips. That is needed anyway, because the bundles carry a copy of the fork's installer.

**Tag.** No need to move `v3.2.2-ro1`. Coaches run the installer copied into the zip from the fork's working tree, not the copy inside the tag. The tag's code, which is what gets installed, is unchanged by these edits. Rebuild the zips after the commit.

## Decisions for Luke

1. Approve Phase 1 as above?
2. Should Phase 1 include the tp-analysis edits (G1–G6, E1 and the zip rebuild)? Or only the fork and the Desktop guide?
3. CG 4.3: reword it (C3) or drop it, given that 4.2 already shows the email?

---

# Phase 1 — 2026-10-18

Luke's rulings:
- Apply the fork docs, the README allowlist, the Desktop guide and the installer closing line.
- Drop guide 4.3.
- Leave `GIRONA-ENGINE-INSTALL.md` and `build_girona_zip.sh` to the engine window (G1–G6 and E1 are handed over as written above, not applied).

## Applied

| File | Change |
|---|---|
| `scripts/install-macos.command` | The closing line now reads: ask `"Am I signed in to TrainingPeaks?"` |
| `README.md` | R1: the allowlist names `tp_refresh_manifest` and `tp_review_manifest` (by exact name) and says what they write. R2: `TP_INSTALL_PYTHON` added to the maintainer overrides. |
| `~/Desktop/S2S/TP-CLAUDE-CONNECTOR-COACH-GUIDE.md` (not in a repo) | **C1:** 3.1 lists the Uninstall file, and the `.whl` and Lap-Placement files that some groups get. **C2:** 4.2 asks *"Am I signed in to TrainingPeaks?"* and says the email must be the coach account. **4.3 dropped:** the old 4.4 is now 4.3. **C4:** section 7 says *"Please refresh my TrainingPeaks sign-in from Chrome."* **C5:** A.2 pins `v3.2.2-ro1`. A copy of the guide as it was before these edits is in the session scratchpad. |
| `docs/reports/FORK-DOCS-AND-INSTALLER-2026-10-18.md` | new (this report) |

## Checks

- **No tool names or old tags left in the guide.** A grep for `tp_…` tool names and for `v3.2.1` finds nothing. The only `tp-mcp` left is the `auth-clear` command in section 6.
- **Installer:** `bash -n` passes on `install-macos.command`.
- **Tests:** `pytest tests/test_install_scripts.py tests/test_install_upgrade.py` gives **28 passed**.

## Tag

**Don't move `v3.2.2-ro1`.** The installed code is unchanged. The closing line reaches coaches only through a zip rebuilt from the fork's working tree. The engine window should rebuild the zips after this commit, together with E1.
