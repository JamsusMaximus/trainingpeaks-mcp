"""The macOS installer run end to end against a stub Python, pip and tp-mcp.

The real install-macos.command runs with HOME in a temp folder, the connector
source from a local tarball and TP_INSTALL_PYTHON pointing at a stub whose
`-m venv` builds a fake environment. The fake tp-mcp answers `auth-status`
with a scripted state and records every call, so the sign-in decisions in
step 6 can be checked without a network, a browser or the Keychain.
"""

import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "scripts" / "install-macos.command"
EMAIL = "coach@example.com"

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="bash installer")

FAKE_PYTHON = """#!/bin/bash
# Stands in for python3: `-m venv DIR` builds a stub venv, anything else is real Python.
if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then
    mkdir -p "$3/bin"
    cp "$STUB_DIR/venv-python" "$3/bin/python"
    chmod +x "$3/bin/python"
    exit 0
fi
exec "$REAL_PY" "$@"
"""

VENV_PYTHON = """#!/bin/bash
echo "python $*" >> "$CALLS"
BIN="$(cd "$(dirname "$0")" && pwd)"
case "$1" in
    -m)
        if [ "$2" = pip ]; then
            if [[ " $* " == *" -e "* ]]; then
                cp "$STUB_DIR/tp-mcp" "$BIN/tp-mcp"; chmod +x "$BIN/tp-mcp"
            fi
            exit 0
        fi ;;
    -c) echo 89; exit 0 ;;
    -u)
        case "$2" in
            *signin_from_chrome.py)
                echo "fake sign-in from Chrome"
                if [ "${FAKE_SIGNIN_RC:-1}" = 0 ]; then echo "$FAKE_SIGNIN_EMAIL" > "$3"; fi
                exit "${FAKE_SIGNIN_RC:-1}" ;;
        esac ;;
esac
exec "$REAL_PY" "$@"
"""

# FAKE_STATUS holds one state per auth-status call (the last one repeats).
FAKE_TP_MCP = """#!/bin/bash
echo "tp-mcp $*" >> "$CALLS"
if [ "$1" = auth-status ]; then
    n=$(grep -c '^tp-mcp auth-status' "$CALLS")
    state=$(echo "$FAKE_STATUS" | awk -v n="$n" '{print (n <= NF) ? $n : $NF}')
    case "$state" in
        valid) printf 'Checking authentication status...\\nAuthenticated\\n  Email: %s\\n  Athlete ID: 1\\n  Storage: keyring\\n' "$FAKE_EMAIL"; exit 0 ;;
        none) printf "Not authenticated.\\nRun 'tp-mcp auth' to authenticate.\\n"; exit 1 ;;
        *) printf "Checking authentication status...\\nAuthentication invalid: Session expired\\n"; exit 1 ;;
    esac
fi
exit 1  # any other command (auth, auth-clear) must never run in these tests
"""


def _write_exec(path: Path, text: str) -> Path:
    path.write_text(text)
    path.chmod(0o755)
    return path


def _snapshot(folder: Path) -> dict:
    """Every entry under folder with its bytes, mode and mtime."""
    out = {}
    for p in sorted(folder.rglob("*")):
        st = p.lstat()
        out[str(p.relative_to(folder))] = (p.read_bytes() if p.is_file() else None,
                                           st.st_mode, st.st_mtime_ns)
    return out


@pytest.fixture
def mac(tmp_path):
    """A temp HOME with an existing install, ~/.tp-mcp data and a Desktop config."""
    home = tmp_path / "home"
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    fakepy = _write_exec(stubs / "python3", FAKE_PYTHON)
    _write_exec(stubs / "venv-python", VENV_PYTHON)
    _write_exec(stubs / "tp-mcp", FAKE_TP_MCP)

    # Connector source as the release tarball would hold it (one top folder).
    src = tmp_path / "src" / "trainingpeaks-mcp-test"
    (src / "scripts").mkdir(parents=True)
    shutil.copy(ROOT / "pyproject.toml", src)
    shutil.copy(ROOT / "scripts" / "_merge_desktop_config.py", src / "scripts")
    tarball = tmp_path / "src.tar.gz"
    with tarfile.open(tarball, "w:gz") as tf:
        tf.add(src, arcname=src.name)

    # The installer runs from its own folder, as from an unpacked zip.
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    installer = bundle / "Install.command"
    shutil.copy(INSTALLER, installer)
    installer.chmod(0o755)

    # An earlier install, downloaded data, and a config with another server.
    old = home / "claude-tools" / "trainingpeaks-mcp"
    old.mkdir(parents=True)
    (old / "OLD-INSTALL").write_text("v3.1.0-ro1")
    data = home / ".tp-mcp"
    (data / "store").mkdir(parents=True)
    (data / "store" / "3979405260.jsonl").write_text('{"row": 1}\n')
    (data / "archive" / "3979405260").mkdir(parents=True)
    (data / "archive" / "3979405260" / "w1.json").write_text("{}")
    (data / "reports").mkdir()
    config = home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"mcpServers": {
        "other": {"command": "/bin/other", "args": ["x"]},
        "trainingpeaks": {"command": "/old/tp-mcp", "args": ["serve", "--read-only"]}}}))

    calls = tmp_path / "calls.log"
    calls.touch()
    env = {
        "HOME": str(home), "PATH": os.environ["PATH"], "LANG": "C",
        "TP_INSTALL_PYTHON": str(fakepy), "TP_MCP_TARBALL": str(tarball),
        "TP_INSTALL_NO_PAUSE": "1", "TP_INSTALL_SKIP_APP": "1",
        "TP_INSTALL_NO_PYTHON_DOWNLOAD": "1",
        "REAL_PY": sys.executable, "STUB_DIR": str(stubs), "CALLS": str(calls),
        "FAKE_EMAIL": EMAIL, "FAKE_STATUS": "valid",
    }

    def run(**extra):
        r = subprocess.run(["bash", str(installer)], env={**env, **extra},
                           capture_output=True, text=True, timeout=120)
        return SimpleNamespace(rc=r.returncode, out=r.stdout + r.stderr,
                               calls=calls.read_text().splitlines())

    return SimpleNamespace(home=home, data=data, config=config, run=run,
                           tools=home / "claude-tools",
                           account=home / "claude-tools" / ".trainingpeaks-account")


def _signin_calls(calls):
    return [c for c in calls if "signin_from_chrome.py" in c]


def _browser_auth_calls(calls):
    return [c for c in calls if c.startswith("tp-mcp auth ") or c == "tp-mcp auth"]


def test_upgrade_with_valid_signin_keeps_it_and_touches_no_data(mac):
    data_before = _snapshot(mac.data)

    r = mac.run(FAKE_STATUS="valid")

    assert r.rc == 0, r.out
    assert "SUCCESS: the TrainingPeaks connector is installed." in r.out
    assert "Existing TrainingPeaks sign-in kept (coach@example.com). Chrome was not read." in r.out
    assert "FAILURE" not in r.out
    # No sign-in of any kind was attempted: only the read-only status check ran.
    assert _signin_calls(r.calls) == []
    assert _browser_auth_calls(r.calls) == []
    assert [c for c in r.calls if c.startswith("tp-mcp ")] == ["tp-mcp auth-status"]
    # ~/.tp-mcp is byte-for-byte, mode and mtime the same.
    assert _snapshot(mac.data) == data_before
    # The earlier install was moved aside, not deleted.
    (old,) = mac.tools.glob("trainingpeaks-mcp.old-*")
    assert (old / "OLD-INSTALL").read_text() == "v3.1.0-ro1"
    # The config was merged: our entry updated, the other server kept.
    servers = json.loads(mac.config.read_text())["mcpServers"]
    assert servers["other"] == {"command": "/bin/other", "args": ["x"]}
    assert servers["trainingpeaks"] == {
        "command": str(mac.tools / "trainingpeaks-mcp" / ".venv" / "bin" / "tp-mcp"),
        "args": ["serve", "--read-only"]}
    # The account is noted (an email only) for a later expired-sign-in comparison.
    assert mac.account.read_text() == EMAIL + "\n"


def test_fresh_signin_has_no_previous_account(mac):
    r = mac.run(FAKE_STATUS="none", FAKE_SIGNIN_RC="0", FAKE_SIGNIN_EMAIL=EMAIL)

    assert r.rc == 0, r.out
    (call,) = _signin_calls(r.calls)
    assert "--previous" not in call
    assert "Signed in to TrainingPeaks as:  coach@example.com" in r.out
    assert mac.account.read_text() == EMAIL + "\n"


def test_expired_signin_passes_the_recorded_account(mac):
    mac.account.write_text(EMAIL + "\n")

    r = mac.run(FAKE_STATUS="invalid", FAKE_SIGNIN_RC="0", FAKE_SIGNIN_EMAIL=EMAIL)

    assert r.rc == 0, r.out
    (call,) = _signin_calls(r.calls)
    assert call.endswith(f"--previous {EMAIL}")
    assert "no longer works (Session expired)" in r.out


def test_expired_signin_without_a_record_is_unknown(mac):
    r = mac.run(FAKE_STATUS="invalid", FAKE_SIGNIN_RC="0", FAKE_SIGNIN_EMAIL=EMAIL)

    (call,) = _signin_calls(r.calls)
    assert call.endswith("--previous-unknown")


def test_declined_replacement_is_not_success_and_not_failure(mac):
    mac.account.write_text(EMAIL + "\n")

    r = mac.run(FAKE_STATUS="invalid", FAKE_SIGNIN_RC="3")

    assert r.rc == 0, r.out
    assert "INSTALLED, NOT SIGNED IN" in r.out
    assert "SUCCESS" not in r.out and "FAILURE" not in r.out
    assert mac.account.read_text() == EMAIL + "\n"  # unchanged


def test_failed_signin_with_working_old_signin_is_not_failure(mac):
    data_before = _snapshot(mac.data)

    r = mac.run(FAKE_STATUS="invalid valid", FAKE_SIGNIN_RC="1")

    assert r.rc == 0, r.out
    assert "FAILURE" not in r.out
    assert "The connector works with the existing sign-in." in r.out
    assert "SUCCESS: the TrainingPeaks connector is installed. Existing TrainingPeaks sign-in kept" in r.out
    assert _snapshot(mac.data) == data_before


def test_failed_signin_with_no_working_signin_is_failure(mac):
    r = mac.run(FAKE_STATUS="invalid", FAKE_SIGNIN_RC="1")

    assert r.rc == 1
    assert "FAILURE: the install stopped while signing in to TrainingPeaks" in r.out


# ---------------------------------------------------------------- the embedded sign-in helper

def _load_signin(monkeypatch, *, chrome_email=EMAIL, valid=True, answer=None):
    text = INSTALLER.read_text()
    start = text.index("<<'SIGNIN_PY'\n") + len("<<'SIGNIN_PY'\n")
    source = text[start:text.index("\nSIGNIN_PY\n", start)]
    ns = {"__name__": "signin_from_chrome"}
    exec(compile(source, "signin_from_chrome.py", "exec"), ns)

    stored = []
    ns["extract_tp_cookie"] = lambda browser: SimpleNamespace(success=True, cookie="c00kie", message="")
    ns["validate_auth_sync"] = lambda cookie: SimpleNamespace(
        is_valid=valid, email=chrome_email, message="Session expired")
    ns["store_credential"] = lambda cookie: stored.append(cookie) or SimpleNamespace(success=True, message="")
    asked = []

    def fake_input(prompt):
        asked.append(prompt)
        return answer

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.delenv("TP_INSTALL_NO_PAUSE", raising=False)
    return ns, stored, asked


def test_signin_same_account_replaces_without_asking(monkeypatch, tmp_path):
    ns, stored, asked = _load_signin(monkeypatch, chrome_email="Coach@Example.com")
    assert ns["main"]([str(tmp_path / "r"), "--previous", EMAIL]) == 0
    assert stored == ["c00kie"] and asked == []
    assert (tmp_path / "r").read_text() == "Coach@Example.com\n"


@pytest.mark.parametrize("answer, rc, n_stored", [("n", 3, 0), ("", 3, 0), ("y", 0, 1)])
def test_signin_different_account_asks(monkeypatch, tmp_path, capsys, answer, rc, n_stored):
    ns, stored, asked = _load_signin(monkeypatch, chrome_email="athlete@example.com", answer=answer)
    assert ns["main"]([str(tmp_path / "r"), "--previous", EMAIL]) == rc
    out = capsys.readouterr().out
    assert "Previous sign-in (expired):  coach@example.com" in out
    assert "Chrome is signed in as:      athlete@example.com" in out
    assert len(asked) == 1 and len(stored) == n_stored
    assert (tmp_path / "r").exists() == (rc == 0)


def test_signin_unknown_previous_asks(monkeypatch, tmp_path, capsys):
    ns, stored, asked = _load_signin(monkeypatch, answer="n")
    assert ns["main"]([str(tmp_path / "r"), "--previous-unknown"]) == 3
    assert "Previous sign-in (expired):  unknown" in capsys.readouterr().out
    assert stored == []


def test_signin_no_previous_does_not_ask(monkeypatch, tmp_path):
    ns, stored, asked = _load_signin(monkeypatch, chrome_email="anyone@example.com")
    assert ns["main"]([str(tmp_path / "r")]) == 0
    assert asked == [] and stored == ["c00kie"]


def test_signin_without_a_terminal_declines(monkeypatch, tmp_path):
    ns, stored, asked = _load_signin(monkeypatch, chrome_email="athlete@example.com", answer="y")
    monkeypatch.setenv("TP_INSTALL_NO_PAUSE", "1")
    assert ns["main"]([str(tmp_path / "r"), "--previous", EMAIL]) == 3
    assert asked == [] and stored == []


def test_signin_invalid_chrome_cookie_stores_nothing(monkeypatch, tmp_path):
    ns, stored, asked = _load_signin(monkeypatch, valid=False)
    assert ns["main"]([str(tmp_path / "r"), "--previous", EMAIL]) == 1
    assert stored == [] and not (tmp_path / "r").exists()
