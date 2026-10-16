"""Tests for the tp_mcp.plugins entry-point hook.

Two layers:
1. _load_plugins() in-process with a patched entry_points(): the skip rules
   (import failure, malformed pairs, name collisions) and the happy path.
2. End to end in a subprocess: a throwaway distribution on PYTHONPATH that
   declares a real entry point, so the importlib.metadata discovery, the
   athlete injection, the metadata derivation and the read-only predicate are
   all exercised on the real module without reloading it in this process.
"""

import json
import subprocess
import sys
import textwrap
from unittest.mock import AsyncMock, MagicMock

from mcp.types import Tool

from tp_mcp import server


def _tool(name: str) -> Tool:
    return Tool(name=name, description=f"{name} (test)", input_schema={"type": "object", "properties": {}})


def _ep(name: str, loader):
    ep = MagicMock()
    ep.name = name
    ep.load.return_value = loader
    return ep


class TestLoadPlugins:
    def test_happy_path(self, monkeypatch):
        handler = AsyncMock()
        monkeypatch.setattr(server, "entry_points",
                            lambda group: [_ep("p", lambda: [(_tool("tp_get_x"), handler)])])
        found = server._load_plugins()
        assert [t.name for t, _ in found] == ["tp_get_x"]
        assert found[0][1] is handler

    def test_import_failure_is_skipped(self, monkeypatch, caplog):
        def boom():
            raise RuntimeError("no engine here")

        monkeypatch.setattr(server, "entry_points",
                            lambda group: [_ep("bad", boom), _ep("ok", lambda: [(_tool("tp_get_y"), AsyncMock())])])
        found = server._load_plugins()
        assert [t.name for t, _ in found] == ["tp_get_y"]
        assert "Plugin bad failed to load" in caplog.text

    def test_malformed_entries_are_skipped(self, monkeypatch, caplog):
        monkeypatch.setattr(
            server,
            "entry_points",
            lambda group: [_ep("p", lambda: ["not a pair", (_tool("tp_get_z"), "not callable"),
                                             (_tool("tp_get_ok"), AsyncMock())])],
        )
        found = server._load_plugins()
        assert [t.name for t, _ in found] == ["tp_get_ok"]
        assert caplog.text.count("malformed entry") == 2

    def test_collision_with_builtin_is_skipped(self, monkeypatch, caplog):
        monkeypatch.setattr(server, "entry_points",
                            lambda group: [_ep("p", lambda: [(_tool("tp_get_workouts"), AsyncMock())])])
        assert server._load_plugins() == []
        assert "collides with an existing tool" in caplog.text

    def test_collision_between_plugins_keeps_first(self, monkeypatch, caplog):
        monkeypatch.setattr(
            server,
            "entry_points",
            lambda group: [_ep("a", lambda: [(_tool("tp_get_dup"), AsyncMock())]),
                           _ep("b", lambda: [(_tool("tp_get_dup"), AsyncMock())])],
        )
        found = server._load_plugins()
        assert len(found) == 1
        assert "Plugin b: tool tp_get_dup collides" in caplog.text

    def test_no_plugins_installed_is_a_noop(self, monkeypatch):
        monkeypatch.setattr(server, "entry_points", lambda group: [])
        assert server._load_plugins() == []


_DUMMY_MODULE = '''
from mcp.types import Tool

async def read_handler(args):
    return {"echo": args}

async def write_handler(args):
    return {"should": "never run under read-only"}

def tools():
    return [
        (Tool(name="tp_get_dummy_plugin", description="dummy read",
              input_schema={"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}),
         read_handler),
        (Tool(name="tp_delete_dummy_plugin", description="dummy write",
              input_schema={"type": "object", "properties": {}}),
         write_handler),
    ]
'''

_PROBE = '''
import asyncio, json, os
from tp_mcp import server
from tp_mcp.server import call_tool, list_tools

async def main():
    out = {}
    names_rw = {t.name for t in await list_tools()}
    out["rw_has_read"] = "tp_get_dummy_plugin" in names_rw
    out["rw_has_write"] = "tp_delete_dummy_plugin" in names_rw
    t = next(x for x in server.TOOLS if x.name == "tp_get_dummy_plugin")
    out["athlete_injected"] = "athlete" in t.input_schema["properties"]
    out["title"] = t.title
    out["read_only_hint"] = t.annotations.read_only_hint
    w = next(x for x in server.TOOLS if x.name == "tp_delete_dummy_plugin")
    out["write_read_only_hint"] = w.annotations.read_only_hint
    r = json.loads((await call_tool("tp_get_dummy_plugin", {"x": "1", "athlete": "Someone"}))[0].text)
    out["dispatch_rw"] = r
    r = json.loads((await call_tool("tp_get_dummy_plugin", {}))[0].text)
    out["missing_arg"] = r["error_code"]
    server.set_read_only_mode(True)
    names_ro = {t.name for t in await list_tools()}
    out["ro_has_read"] = "tp_get_dummy_plugin" in names_ro
    out["ro_has_write"] = "tp_delete_dummy_plugin" in names_ro
    r = json.loads((await call_tool("tp_delete_dummy_plugin", {}))[0].text)
    out["ro_write_dispatch"] = r["error_code"]
    r = json.loads((await call_tool("tp_get_dummy_plugin", {"x": "2"}))[0].text)
    out["ro_read_dispatch"] = r
    print(json.dumps(out))

asyncio.run(main())
'''


def _fake_distribution(root):
    """A minimal installed distribution: a module plus a .dist-info with an
    entry_points.txt, which is all importlib.metadata needs to discover it."""
    (root / "dummy_tp_plugin.py").write_text(_DUMMY_MODULE)
    info = root / "dummy_tp_plugin-0.0.1.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: dummy-tp-plugin\nVersion: 0.0.1\n")
    (info / "entry_points.txt").write_text("[tp_mcp.plugins]\ndummy = dummy_tp_plugin:tools\n")


class TestEntryPointEndToEnd:
    def test_dummy_plugin_is_registered_like_a_builtin(self, tmp_path):
        _fake_distribution(tmp_path)
        proc = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(_PROBE)],
            capture_output=True,
            text=True,
            env={**__import__("os").environ, "PYTHONPATH": str(tmp_path), "TP_MCP_SKIP_STARTUP_VALIDATION": "1"},
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr[-2000:]
        out = json.loads(proc.stdout.strip().splitlines()[-1])

        # Read-write: both plugin tools present, finalised like built-ins.
        assert out["rw_has_read"] and out["rw_has_write"]
        assert out["athlete_injected"] is True
        assert out["title"] == "Get dummy plugin"
        assert out["read_only_hint"] is True
        assert out["write_read_only_hint"] is False
        assert out["dispatch_rw"] == {"echo": {"x": "1"}}  # athlete popped by call_tool
        assert out["missing_arg"] == "INVALID_ARGS"

        # Read-only: the predicate applies by name, listing and dispatch alike.
        assert out["ro_has_read"] is True
        assert out["ro_has_write"] is False
        assert out["ro_write_dispatch"] == "READ_ONLY_MODE"
        assert out["ro_read_dispatch"] == {"echo": {"x": "2"}}
