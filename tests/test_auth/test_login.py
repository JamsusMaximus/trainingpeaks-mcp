"""Tests for opt-in username/password login."""

import httpx
import pytest

from tp_mcp.auth import login

FORM = '<form><input type="hidden" name="__RequestVerificationToken" value="tok123"></form>'


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("TP_USERNAME", raising=False)
    monkeypatch.delenv("TP_PASSWORD", raising=False)
    monkeypatch.delenv("TP_AUTH_COOKIE", raising=False)
    login.clear_session()
    yield
    login.clear_session()


def _patch_transport(monkeypatch, handler):
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(login.httpx, "AsyncClient", factory)


def test_env_credentials_require_both(monkeypatch):
    assert login.env_credentials() is None
    monkeypatch.setenv("TP_USERNAME", "coach")
    assert login.env_credentials() is None
    monkeypatch.setenv("TP_PASSWORD", "pw")
    assert login.env_credentials() == ("coach", "pw")


@pytest.mark.asyncio
async def test_login_success_returns_cookie(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text=FORM)
        seen["body"] = request.content.decode()
        return httpx.Response(200, text="ok", headers={"set-cookie": "Production_tpAuth=abc; Path=/"})

    _patch_transport(monkeypatch, handler)
    result = await login.login_with_password("coach", "pw")
    assert result.success and result.cookie == "abc"
    assert "__RequestVerificationToken=tok123" in seen["body"]
    assert "abc" not in repr(result)


@pytest.mark.asyncio
async def test_login_failure_never_leaks_password(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=FORM if request.method == "GET" else "bad")

    _patch_transport(monkeypatch, handler)
    result = await login.login_with_password("coach", "s3cret-pw")
    assert not result.success
    assert "s3cret-pw" not in result.message


@pytest.mark.asyncio
async def test_missing_form_token(monkeypatch):
    _patch_transport(monkeypatch, lambda r: httpx.Response(200, text="<html></html>"))
    result = await login.login_with_password("coach", "pw")
    assert not result.success


@pytest.mark.asyncio
async def test_session_cached_in_memory_only(monkeypatch):
    monkeypatch.setenv("TP_USERNAME", "coach")
    monkeypatch.setenv("TP_PASSWORD", "pw")
    calls = {"n": 0}

    async def fake_login(u, p):
        calls["n"] += 1
        return login.LoginResult(True, cookie="c1")

    monkeypatch.setattr(login, "login_with_password", fake_login)
    assert (await login.get_session_cookie()).cookie == "c1"
    assert (await login.get_session_cookie()).cookie == "c1"
    assert calls["n"] == 1
    await login.get_session_cookie(force_refresh=True)
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_resolve_cookie_precedence(monkeypatch):
    monkeypatch.setenv("TP_USERNAME", "coach")
    monkeypatch.setenv("TP_PASSWORD", "pw")

    async def fake_login(u, p):
        return login.LoginResult(True, cookie="from-login")

    monkeypatch.setattr(login, "login_with_password", fake_login)
    assert await login.resolve_cookie() == ("from-login", True)
    monkeypatch.setenv("TP_AUTH_COOKIE", "explicit")
    assert await login.resolve_cookie() == ("explicit", False)


@pytest.mark.asyncio
async def test_failed_login_not_retried_during_cooldown(monkeypatch):
    monkeypatch.setenv("TP_USERNAME", "coach")
    monkeypatch.setenv("TP_PASSWORD", "wrong")
    calls = {"n": 0}

    async def fake_login(u, p):
        calls["n"] += 1
        return login.LoginResult(False, message="nope")

    monkeypatch.setattr(login, "login_with_password", fake_login)
    assert not (await login.get_session_cookie()).success
    assert not (await login.get_session_cookie()).success
    assert calls["n"] == 1
    assert not (await login.get_session_cookie(force_refresh=True)).success
    assert calls["n"] == 2
