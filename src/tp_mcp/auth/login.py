"""Opt-in username/password login for TrainingPeaks.

SECURITY NOTES:
- Credentials are read ONLY from the TP_USERNAME and TP_PASSWORD environment
  variables, supplied by the caller (for example a launcher that reads the OS keyring). They
  are never written to the keyring, the encrypted file, or disk.
- The session cookie obtained from a login is held in process memory only.
- Neither the password nor the cookie may appear in messages or logs.
- Accounts that require 2FA, a CAPTCHA, or social sign-in cannot use this path.
"""

import asyncio
import os
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser

import httpx

LOGIN_URL = "https://home.trainingpeaks.com/login"
COOKIE_NAME = "Production_tpAuth"
LOGIN_TIMEOUT = 15.0
USERNAME_ENV = "TP_USERNAME"
PASSWORD_ENV = "TP_PASSWORD"

FAILURE_COOLDOWN = 300.0

_session_cookie: str | None = None
_failed_until: float = 0.0
_login_lock = asyncio.Lock()


@dataclass
class LoginResult:
    """Result of a password login. The cookie never appears in repr or message."""

    success: bool
    cookie: str | None = field(default=None, repr=False)
    message: str = ""


class _TokenParser(HTMLParser):
    """Finds the anti-forgery token in the login form."""

    def __init__(self) -> None:
        super().__init__()
        self.token: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "input":
            return
        attr = dict(attrs)
        if attr.get("name") == "__RequestVerificationToken" and attr.get("value"):
            self.token = attr["value"]


def env_credentials() -> tuple[str, str] | None:
    """Return (username, password) from the environment, or None if either is unset."""
    username = os.environ.get(USERNAME_ENV, "").strip()
    password = os.environ.get(PASSWORD_ENV, "")
    if username and password:
        return username, password
    return None


def has_env_credentials() -> bool:
    """Whether username/password login is configured through the environment."""
    return env_credentials() is not None


async def login_with_password(username: str, password: str) -> LoginResult:
    """Log in through the web form and return the Production_tpAuth cookie.

    Args:
        username: TrainingPeaks username or email.
        password: TrainingPeaks password.

    Returns:
        LoginResult with the cookie on success. Messages never contain credentials.
    """
    try:
        async with httpx.AsyncClient(timeout=LOGIN_TIMEOUT, follow_redirects=True) as client:
            page = await client.get(LOGIN_URL)
            parser = _TokenParser()
            parser.feed(page.text)
            if not parser.token:
                return LoginResult(False, message="Could not read the TrainingPeaks login form.")

            response = await client.post(
                LOGIN_URL,
                data={
                    "__RequestVerificationToken": parser.token,
                    "CaptchaHidden": "true",
                    "CaptchaToken": "",
                    "Attempts": "",
                    "SelectedMfaMethod": "",
                    "Username": username,
                    "Password": password,
                },
            )
            cookie = client.cookies.get(COOKIE_NAME)
            if cookie:
                return LoginResult(True, cookie=cookie, message="Login succeeded")

            if response.status_code in (401, 403):
                return LoginResult(False, message="Login rejected by TrainingPeaks.")
            return LoginResult(
                False,
                message=(
                    "Login did not return a session. Check the username and password. "
                    "Accounts with 2FA, a CAPTCHA, or social sign-in cannot use password login."
                ),
            )
    except httpx.TimeoutException:
        return LoginResult(False, message="Login request timed out.")
    except httpx.RequestError as e:
        return LoginResult(False, message=f"Network error during login: {type(e).__name__}")


async def get_session_cookie(force_refresh: bool = False) -> LoginResult:
    """Return the in-memory session cookie, logging in from the environment if needed.

    A failed login is not retried for FAILURE_COOLDOWN seconds, so a wrong
    password cannot hammer the login endpoint (and lock the account) on every
    tool call. Concurrent callers share a single login.

    Args:
        force_refresh: Discard any cached session and cooldown, and log in again.
    """
    global _session_cookie, _failed_until
    creds = env_credentials()
    if creds is None:
        return LoginResult(False, message="TP_USERNAME and TP_PASSWORD are not both set.")
    async with _login_lock:
        if _session_cookie and not force_refresh:
            return LoginResult(True, cookie=_session_cookie, message="Using in-memory session")
        if not force_refresh and time.monotonic() < _failed_until:
            return LoginResult(False, message="Password login failed recently; not retrying yet.")
        result = await login_with_password(*creds)
        _session_cookie = result.cookie if result.success else None
        _failed_until = 0.0 if result.success else time.monotonic() + FAILURE_COOLDOWN
        return result


def clear_session() -> None:
    """Forget the in-memory session cookie."""
    global _session_cookie, _failed_until
    _session_cookie = None
    _failed_until = 0.0


async def resolve_cookie() -> tuple[str | None, bool]:
    """Pick the session cookie to use.

    Order: TP_AUTH_COOKIE, then TP_USERNAME/TP_PASSWORD login (kept in memory
    only), then the stored keyring/encrypted-file credential.

    Returns:
        (cookie or None, whether it came from a password login)
    """
    from tp_mcp.auth.storage import ENV_VAR_NAME, get_credential

    if os.environ.get(ENV_VAR_NAME):
        return os.environ[ENV_VAR_NAME], False
    if has_env_credentials():
        result = await get_session_cookie()
        return (result.cookie if result.success else None), True
    cred = get_credential()
    return (cred.cookie if cred.success else None), False
