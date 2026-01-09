"""Security tests for tp_refresh_auth tool.

These tests verify that cookie values can NEVER leak into tool output.
"""

import pytest

from tp_mcp.tools.refresh_auth import _sanitize_result


class TestSanitizeResult:
    """Test the result sanitization function."""

    def test_removes_cookie_key(self):
        """Cookie values must never appear in output."""
        result = {
            "success": True,
            "cookie": "SENSITIVE_VALUE_12345",
            "message": "OK",
        }
        sanitized = _sanitize_result(result)
        assert "cookie" not in sanitized
        assert "SENSITIVE_VALUE" not in str(sanitized)

    def test_removes_auth_token_key(self):
        """Auth-related keys must be stripped."""
        result = {
            "success": True,
            "auth_token": "secret123",
            "token": "secret456",
            "message": "OK",
        }
        sanitized = _sanitize_result(result)
        assert "auth_token" not in sanitized
        assert "token" not in sanitized
        assert "secret" not in str(sanitized).lower()

    def test_removes_credential_key(self):
        """Credential keys must be stripped."""
        result = {
            "success": True,
            "credential": "mycred",
            "user_credential": "othercred",
            "message": "OK",
        }
        sanitized = _sanitize_result(result)
        assert "credential" not in sanitized
        assert "user_credential" not in sanitized

    def test_preserves_safe_keys(self):
        """Safe keys should be preserved."""
        result = {
            "success": True,
            "message": "Authentication refreshed",
            "athlete_id": 12345,
            "email": "test@example.com",
            "browser": "chrome",
        }
        sanitized = _sanitize_result(result)
        assert sanitized == result

    def test_case_insensitive_filtering(self):
        """Filtering should be case-insensitive."""
        result = {
            "success": True,
            "COOKIE": "value1",
            "Cookie": "value2",
            "AUTH_TOKEN": "value3",
            "message": "OK",
        }
        sanitized = _sanitize_result(result)
        assert "COOKIE" not in sanitized
        assert "Cookie" not in sanitized
        assert "AUTH_TOKEN" not in sanitized


class TestBrowserCookieResultRepr:
    """Test that BrowserCookieResult doesn't leak cookies in repr."""

    def test_repr_hides_cookie_value(self):
        """Cookie value must not appear in repr."""
        from tp_mcp.auth.browser import BrowserCookieResult

        result = BrowserCookieResult(
            success=True,
            cookie="SUPER_SECRET_COOKIE_VALUE_12345",
            browser="chrome",
            message="Found cookie",
        )
        repr_str = repr(result)
        assert "SUPER_SECRET" not in repr_str
        assert "12345" not in repr_str
        assert "cookie=<present>" in repr_str

    def test_repr_shows_none_for_missing_cookie(self):
        """Repr should indicate when cookie is None."""
        from tp_mcp.auth.browser import BrowserCookieResult

        result = BrowserCookieResult(success=False, message="Not found")
        repr_str = repr(result)
        assert "cookie=<None>" in repr_str
