"""Tests for coach account support: context var, ensure_athlete_id, schema injection."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.context import athlete_override
from tp_mcp.client.http import TPClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

COACH_USER_DATA = {
    "personId": 100,
    "firstName": "Stevan",
    "lastName": "Coach",
    "email": "stevan@example.com",
    "athletes": [
        {
            "athleteId": 100,
            "firstName": "Stevan",
            "lastName": "Coach",
            "email": "stevan@example.com",
            "coachedBy": 100,
        },
        {
            "athleteId": 201,
            "firstName": "Charlotte",
            "lastName": "Horton",
            "email": "charlotte@example.com",
            "coachedBy": 100,
        },
        {
            "athleteId": 302,
            "firstName": "Alice",
            "lastName": "Runner",
            "email": "alice@example.com",
            "coachedBy": 100,
        },
    ],
}

SOLO_USER_DATA = {
    "personId": 500,
    "firstName": "Solo",
    "lastName": "Athlete",
    "email": "solo@example.com",
    "athletes": [],
}


@pytest.fixture(autouse=True)
def _clear_caches():
    """Reset class-level caches between tests."""
    TPClient._cached_athlete_id = None
    TPClient._cached_user_data = None
    yield
    TPClient._cached_athlete_id = None
    TPClient._cached_user_data = None


def _mock_client(user_data):
    """Create a TPClient with mocked _get_user_data."""
    client = TPClient.__new__(TPClient)
    client._athlete_id = None
    client._get_user_data = AsyncMock(return_value=user_data)
    return client


# ---------------------------------------------------------------------------
# Context variable lifecycle
# ---------------------------------------------------------------------------

class TestAthleteOverrideContextVar:
    def test_default_is_none(self):
        assert athlete_override.get() is None

    def test_set_and_reset(self):
        token = athlete_override.set("Charlotte Horton")
        assert athlete_override.get() == "Charlotte Horton"
        athlete_override.reset(token)
        assert athlete_override.get() is None

    def test_nested_set_reset(self):
        t1 = athlete_override.set("Alice")
        t2 = athlete_override.set("Bob")
        assert athlete_override.get() == "Bob"
        athlete_override.reset(t2)
        assert athlete_override.get() == "Alice"
        athlete_override.reset(t1)
        assert athlete_override.get() is None


# ---------------------------------------------------------------------------
# ensure_athlete_id — no override (coach's own)
# ---------------------------------------------------------------------------

class TestEnsureAthleteIdNoOverride:
    @pytest.mark.asyncio
    async def test_resolves_to_coach_own_entry(self):
        client = _mock_client(COACH_USER_DATA)
        aid = await client.ensure_athlete_id()
        assert aid == 100

    @pytest.mark.asyncio
    async def test_caches_when_no_override(self):
        client = _mock_client(COACH_USER_DATA)
        await client.ensure_athlete_id()
        assert TPClient._cached_athlete_id == 100

    @pytest.mark.asyncio
    async def test_uses_cache_on_second_call(self):
        client = _mock_client(COACH_USER_DATA)
        await client.ensure_athlete_id()
        # Second call should use cache, not call _get_user_data again
        client2 = _mock_client(COACH_USER_DATA)
        TPClient._cached_athlete_id = 100  # simulate cache from first call
        aid = await client2.ensure_athlete_id()
        assert aid == 100
        client2._get_user_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_solo_account_uses_person_id(self):
        client = _mock_client(SOLO_USER_DATA)
        aid = await client.ensure_athlete_id()
        assert aid == 500

    @pytest.mark.asyncio
    async def test_returns_none_on_api_failure(self):
        client = _mock_client(None)
        aid = await client.ensure_athlete_id()
        assert aid is None


# ---------------------------------------------------------------------------
# ensure_athlete_id — with name override
# ---------------------------------------------------------------------------

class TestEnsureAthleteIdNameOverride:
    @pytest.mark.asyncio
    async def test_resolve_by_first_name(self):
        client = _mock_client(COACH_USER_DATA)
        token = athlete_override.set("charlotte")
        try:
            aid = await client.ensure_athlete_id()
            assert aid == 201
        finally:
            athlete_override.reset(token)

    @pytest.mark.asyncio
    async def test_resolve_by_last_name(self):
        client = _mock_client(COACH_USER_DATA)
        token = athlete_override.set("Horton")
        try:
            aid = await client.ensure_athlete_id()
            assert aid == 201
        finally:
            athlete_override.reset(token)

    @pytest.mark.asyncio
    async def test_resolve_by_full_name(self):
        client = _mock_client(COACH_USER_DATA)
        token = athlete_override.set("Charlotte Horton")
        try:
            aid = await client.ensure_athlete_id()
            assert aid == 201
        finally:
            athlete_override.reset(token)

    @pytest.mark.asyncio
    async def test_case_insensitive(self):
        client = _mock_client(COACH_USER_DATA)
        token = athlete_override.set("ALICE")
        try:
            aid = await client.ensure_athlete_id()
            assert aid == 302
        finally:
            athlete_override.reset(token)

    @pytest.mark.asyncio
    async def test_unknown_name_returns_none(self):
        client = _mock_client(COACH_USER_DATA)
        token = athlete_override.set("Nobody")
        try:
            aid = await client.ensure_athlete_id()
            assert aid is None
        finally:
            athlete_override.reset(token)

    @pytest.mark.asyncio
    async def test_does_not_cache_when_override_set(self):
        client = _mock_client(COACH_USER_DATA)
        token = athlete_override.set("Charlotte Horton")
        try:
            await client.ensure_athlete_id()
            assert TPClient._cached_athlete_id is None
        finally:
            athlete_override.reset(token)


# ---------------------------------------------------------------------------
# ensure_athlete_id — with ID override
# ---------------------------------------------------------------------------

class TestEnsureAthleteIdIdOverride:
    @pytest.mark.asyncio
    async def test_resolve_by_id(self):
        client = _mock_client(COACH_USER_DATA)
        token = athlete_override.set("201")
        try:
            aid = await client.ensure_athlete_id()
            assert aid == 201
        finally:
            athlete_override.reset(token)

    @pytest.mark.asyncio
    async def test_unknown_id_returns_none(self):
        client = _mock_client(COACH_USER_DATA)
        token = athlete_override.set("999")
        try:
            aid = await client.ensure_athlete_id()
            assert aid is None
        finally:
            athlete_override.reset(token)


# ---------------------------------------------------------------------------
# ensure_athlete_id — cache bypass when override is set
# ---------------------------------------------------------------------------

class TestCacheBypass:
    @pytest.mark.asyncio
    async def test_bypasses_cache_with_override(self):
        """Even if class cache is set, override should re-resolve from user data."""
        TPClient._cached_athlete_id = 100
        client = _mock_client(COACH_USER_DATA)
        token = athlete_override.set("Charlotte Horton")
        try:
            aid = await client.ensure_athlete_id()
            assert aid == 201
            # _get_user_data should be called because cache is bypassed
            client._get_user_data.assert_called_once()
        finally:
            athlete_override.reset(token)


# ---------------------------------------------------------------------------
# Schema injection
# ---------------------------------------------------------------------------

class TestSchemaInjection:
    def test_non_exempt_tools_have_athlete_param(self):
        from tp_mcp.server import TOOLS, _ATHLETE_EXEMPT_TOOLS
        for tool in TOOLS:
            if tool.name not in _ATHLETE_EXEMPT_TOOLS:
                assert "athlete" in tool.inputSchema["properties"], (
                    f"Tool {tool.name} missing 'athlete' property"
                )

    def test_exempt_tools_lack_athlete_param(self):
        from tp_mcp.server import TOOLS, _ATHLETE_EXEMPT_TOOLS
        for tool in TOOLS:
            if tool.name in _ATHLETE_EXEMPT_TOOLS:
                assert "athlete" not in tool.inputSchema["properties"], (
                    f"Exempt tool {tool.name} should not have 'athlete' property"
                )

    def test_tp_list_athletes_in_tools(self):
        from tp_mcp.server import TOOLS
        names = [t.name for t in TOOLS]
        assert "tp_list_athletes" in names


# ---------------------------------------------------------------------------
# call_tool strips athlete and sets context var
# ---------------------------------------------------------------------------

class TestCallToolAthleteStripping:
    @pytest.mark.asyncio
    async def test_athlete_stripped_from_args(self):
        """The athlete key should be removed before reaching the handler."""
        captured_args = {}

        from tp_mcp.server import _TOOL_HANDLERS

        original = _TOOL_HANDLERS.get("tp_auth_status")
        async def spy(args):
            captured_args.update(args)
            return {"status": "ok"}

        _TOOL_HANDLERS["tp_auth_status"] = spy
        try:
            from tp_mcp.server import call_tool
            await call_tool("tp_auth_status", {"athlete": "Charlotte Horton", "extra": "val"})
            assert "athlete" not in captured_args
            assert captured_args.get("extra") == "val"
        finally:
            if original:
                _TOOL_HANDLERS["tp_auth_status"] = original

    @pytest.mark.asyncio
    async def test_context_var_reset_after_call(self):
        """Context var should be None after call_tool completes."""
        from tp_mcp.server import _TOOL_HANDLERS

        original = _TOOL_HANDLERS.get("tp_list_athletes")
        async def stub(args):
            return {"athletes": []}

        _TOOL_HANDLERS["tp_list_athletes"] = stub
        try:
            from tp_mcp.server import call_tool
            await call_tool("tp_list_athletes", {"athlete": "test"})
            assert athlete_override.get() is None
        finally:
            if original:
                _TOOL_HANDLERS["tp_list_athletes"] = original

    @pytest.mark.asyncio
    async def test_context_var_reset_on_error(self):
        """Context var should be reset even if handler raises."""
        from tp_mcp.server import _TOOL_HANDLERS

        original = _TOOL_HANDLERS.get("tp_list_athletes")
        async def exploding(args):
            raise RuntimeError("boom")

        _TOOL_HANDLERS["tp_list_athletes"] = exploding
        try:
            from tp_mcp.server import call_tool
            # Should not raise (call_tool catches exceptions)
            result = await call_tool("tp_list_athletes", {"athlete": "test"})
            assert athlete_override.get() is None
        finally:
            if original:
                _TOOL_HANDLERS["tp_list_athletes"] = original
