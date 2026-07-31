"""Tests for read-only mode (--read-only / TP_MCP_READ_ONLY=1).

Read-only mode is a two-layer, allowlist-based guarantee:
1. Listing: tools failing _is_read_only_tool never appear in tools/list.
2. Dispatch: calling a non-allowlisted name (stale client cache, injection)
   returns an explicit error before any handler or HTTP request runs.
"""

import json
import logging
import sys
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from tp_mcp import cli, server
from tp_mcp.server import (
    TOOLS,
    _is_read_only_tool,
    call_tool,
    list_tools,
    set_read_only_mode,
)


def _parse_result(text_contents: list) -> dict:
    """Extract the JSON dict from a call_tool response."""
    assert len(text_contents) == 1
    return json.loads(text_contents[0].text)


@pytest.fixture(autouse=True)
def _clean_read_only_state(monkeypatch):
    """Each test starts from default mode and cannot leak state."""
    monkeypatch.delenv("TP_MCP_READ_ONLY", raising=False)
    yield
    set_read_only_mode(False)


class TestListing:
    async def test_read_only_list_contains_no_write_tools(self):
        set_read_only_mode(True)
        tools = await list_tools()
        offenders = [t.name for t in tools if not _is_read_only_tool(t.name)]
        assert offenders == []
        # Sanity: the read-only surface is non-trivial, not an empty list.
        assert {"tp_get_workouts", "tp_auth_status"} <= {t.name for t in tools}

    async def test_env_var_activates_read_only_mode(self, monkeypatch):
        monkeypatch.setenv("TP_MCP_READ_ONLY", "1")
        tools = await list_tools()
        assert all(_is_read_only_tool(t.name) for t in tools)
        assert "tp_delete_workout" not in {t.name for t in tools}

    async def test_default_mode_list_is_unchanged(self):
        tools = await list_tools()
        assert tools is TOOLS

    async def test_injected_write_tool_is_excluded(self, monkeypatch):
        """Allowlist semantics: an unknown future write tool is excluded by
        default, without appearing in any blocklist."""
        fake = TOOLS[0].model_copy(update={"name": "tp_wipe_calendar"})
        monkeypatch.setattr(server, "TOOLS", TOOLS + [fake])
        set_read_only_mode(True)
        assert "tp_wipe_calendar" not in {t.name for t in await list_tools()}


class TestDispatch:
    @pytest.mark.parametrize("name", ["tp_create_workout", "tp_delete_workout"])
    async def test_write_call_rejected_without_handler_running(self, monkeypatch, name):
        handler = AsyncMock()
        monkeypatch.setitem(server._TOOL_HANDLERS, name, handler)
        set_read_only_mode(True)

        result = _parse_result(await call_tool(name, {"workout_id": "123"}))

        assert result["isError"] is True
        assert result["error_code"] == "READ_ONLY_MODE"
        assert result["message"] == "Tool disabled: server is running in read-only mode."
        handler.assert_not_awaited()

    async def test_unknown_write_name_rejected(self):
        """Names outside the allowlist are rejected even if never registered."""
        set_read_only_mode(True)
        result = _parse_result(await call_tool("tp_wipe_calendar", {}))
        assert result["error_code"] == "READ_ONLY_MODE"

    async def test_read_tool_still_dispatches(self, monkeypatch):
        handler = AsyncMock(return_value={"ok": True})
        monkeypatch.setitem(server._TOOL_HANDLERS, "tp_get_profile", handler)
        set_read_only_mode(True)

        result = _parse_result(await call_tool("tp_get_profile", {}))

        assert result == {"ok": True}
        handler.assert_awaited_once()

    async def test_default_mode_does_not_reject_writes(self, monkeypatch):
        handler = AsyncMock(return_value={"ok": True})
        monkeypatch.setitem(server._TOOL_HANDLERS, "tp_delete_workout", handler)

        result = _parse_result(await call_tool("tp_delete_workout", {"workout_id": "123"}))

        assert result == {"ok": True}
        handler.assert_awaited_once()


class TestEnvVar:
    @pytest.mark.parametrize("value", ["1", "true", "True", "TRUE", "yes", "YES"])
    async def test_truthy_values_enable(self, monkeypatch, value):
        monkeypatch.setenv("TP_MCP_READ_ONLY", value)
        tools = await list_tools()
        assert tools is not TOOLS
        assert all(_is_read_only_tool(t.name) for t in tools)

    @pytest.mark.parametrize("value", ["0", "false", "False", "no", "NO"])
    async def test_falsy_values_disable(self, monkeypatch, value):
        monkeypatch.setenv("TP_MCP_READ_ONLY", value)
        assert await list_tools() is TOOLS

    async def test_unset_disables(self):
        assert await list_tools() is TOOLS

    @pytest.mark.parametrize("value", ["banana", "2", "on", " "])
    def test_invalid_value_fails_startup(self, monkeypatch, caplog, value):
        """A malformed value must abort startup, never fall back to
        read-write silently."""
        monkeypatch.setenv("TP_MCP_READ_ONLY", value)
        with caplog.at_level(logging.ERROR, logger="tp-mcp"):
            rc = server.run_server()
        assert rc == 1
        assert "Invalid TP_MCP_READ_ONLY value" in caplog.text


class TestCliWiring:
    @pytest.fixture(autouse=True)
    def _no_real_server(self, monkeypatch):
        """cli.main() must never start a real stdio server in tests."""
        monkeypatch.setattr(server, "run_server_async", AsyncMock())

    def test_read_only_flag_reaches_set_read_only_mode(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["tp-mcp", "serve", "--read-only"])
        assert cli.main() == 0
        assert server._read_only_active() is True

    def test_serve_without_flag_stays_read_write(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["tp-mcp", "serve"])
        assert cli.main() == 0
        assert server._read_only_active() is False

    @pytest.mark.parametrize(
        "tail",
        [["--bogus"], ["--read-only", "extra"], ["--READ-ONLY"], ["--read-only", "--read-only"]],
    )
    def test_unknown_serve_argument_exits_nonzero(self, monkeypatch, capsys, tail):
        monkeypatch.setattr(sys, "argv", ["tp-mcp", "serve", *tail])
        assert cli.main() == 1
        err = capsys.readouterr().err
        assert "Error: invalid arguments for serve" in err
        assert "Usage: tp-mcp serve [--read-only]" in err


class TestStartupLog:
    async def test_startup_logs_disabled_tool_count(self, monkeypatch, caplog):
        set_read_only_mode(True)
        monkeypatch.setenv("TP_MCP_SKIP_STARTUP_VALIDATION", "1")

        @asynccontextmanager
        async def fake_stdio():
            yield (MagicMock(), MagicMock())

        monkeypatch.setattr(server, "stdio_server", fake_stdio)
        monkeypatch.setattr(server.server, "run", AsyncMock())
        with caplog.at_level(logging.INFO, logger="tp-mcp"):
            await server.run_server_async()

        expected = sum(1 for t in TOOLS if not _is_read_only_tool(t.name))
        assert f"READ-ONLY MODE: {expected} write tools disabled." in caplog.text
