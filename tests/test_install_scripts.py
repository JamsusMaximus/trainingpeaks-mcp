"""The macOS one-click installer's config merge helper and script hygiene."""

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
HELPER = SCRIPTS / "_merge_desktop_config.py"

_spec = importlib.util.spec_from_file_location("_merge_desktop_config", HELPER)
merge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(merge)

CMD = "/Users/x/claude-tools/trainingpeaks-mcp/.venv/bin/tp-mcp"
ENTRY = {"command": CMD, "args": ["serve", "--read-only"]}


def _run(*args):
    return subprocess.run([sys.executable, str(HELPER), *args], capture_output=True, text=True)


def _backups(path: Path):
    return sorted(p for p in path.parent.iterdir() if p.name.startswith(path.name + ".bak-"))


def test_add_creates_missing_folder_and_file(tmp_path):
    cfg = tmp_path / "Claude" / "claude_desktop_config.json"
    assert merge.add(str(cfg), CMD) == "updated"
    assert json.loads(cfg.read_text()) == {"mcpServers": {"trainingpeaks": ENTRY}}
    assert _backups(cfg) == []  # nothing to back up


def test_add_preserves_other_servers_and_keys_and_backs_up(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    original = {"globalShortcut": "Cmd+Space",
                "mcpServers": {"other": {"command": "/bin/other", "args": ["x"]},
                               "trainingpeaks": {"command": "/old/tp-mcp", "args": ["serve"]}}}
    cfg.write_text(json.dumps(original))
    assert merge.add(str(cfg), CMD) == "updated"
    data = json.loads(cfg.read_text())
    assert data["globalShortcut"] == "Cmd+Space"
    assert data["mcpServers"]["other"] == original["mcpServers"]["other"]
    assert data["mcpServers"]["trainingpeaks"] == ENTRY
    (bak,) = _backups(cfg)
    assert json.loads(bak.read_text()) == original


def test_add_is_idempotent(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    merge.add(str(cfg), CMD)
    before = cfg.read_text()
    assert merge.add(str(cfg), CMD) == "unchanged"
    assert cfg.read_text() == before
    assert _backups(cfg) == []


def test_add_treats_empty_file_as_new(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text("  \n")
    assert merge.add(str(cfg), CMD) == "updated"
    assert json.loads(cfg.read_text())["mcpServers"]["trainingpeaks"] == ENTRY


@pytest.mark.parametrize("body", ['{"mcpServers": {', "[1, 2]", '{"mcpServers": []}'])
def test_invalid_config_is_never_touched(tmp_path, body):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(body)
    r = _run("add", str(cfg), CMD)
    assert r.returncode == 2
    assert r.stderr.strip()
    assert cfg.read_text() == body
    assert _backups(cfg) == []
    assert _run("remove", str(cfg)).returncode == 2
    assert cfg.read_text() == body


def test_remove_keeps_other_servers(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "/bin/o"}, "trainingpeaks": ENTRY}}))
    r = _run("remove", str(cfg))
    assert (r.returncode, r.stdout.strip()) == (0, "removed")
    assert json.loads(cfg.read_text()) == {"mcpServers": {"other": {"command": "/bin/o"}}}
    assert len(_backups(cfg)) == 1


def test_remove_when_absent_writes_nothing(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    assert _run("remove", str(cfg)).stdout.strip() == "absent"
    assert not cfg.exists()


def test_usage_error():
    assert _run("frobnicate").returncode == 1


@pytest.mark.parametrize("name", ["install-macos.command", "uninstall-macos.command"])
def test_scripts_are_executable_bash_and_parse(name):
    path = SCRIPTS / name
    assert os.stat(path).st_mode & stat.S_IXUSR
    assert path.read_text().startswith("#!/bin/bash\n")
    assert subprocess.run(["bash", "-n", str(path)]).returncode == 0


def test_installer_uses_editable_browser_extra_and_read_only():
    text = (SCRIPTS / "install-macos.command").read_text()
    assert 'pip install -e ".[browser]"' in text
    assert 'pip install "tp-mcp[browser]"' not in text
    assert merge.SERVE_ARGS == ["serve", "--read-only"]
