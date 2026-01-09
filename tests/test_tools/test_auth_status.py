"""Tests for tp_auth_status tool."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.auth.keyring import CredentialResult
from tp_mcp.auth.validator import AuthResult, AuthStatus
from tp_mcp.tools.auth_status import tp_auth_status


class TestTpAuthStatus:
    """Tests for tp_auth_status tool."""

    @pytest.mark.asyncio
    async def test_valid_auth(self):
        """Test auth status with valid authentication."""
        mock_cred = CredentialResult(success=True, message="OK", cookie="test_cookie")
        mock_result = AuthResult(
            status=AuthStatus.VALID,
            athlete_id=123,
            email="test@example.com",
        )

        with patch("tp_mcp.tools.auth_status.get_credential", return_value=mock_cred):
            with patch(
                "tp_mcp.tools.auth_status.validate_auth",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                with patch(
                    "tp_mcp.tools.auth_status.get_storage_backend",
                    return_value="keyring",
                ):
                    result = await tp_auth_status()

        assert result["valid"] is True
        assert result["athlete_id"] == 123
        assert result["email"] == "test@example.com"
        assert result["action_needed"] is None

    @pytest.mark.asyncio
    async def test_no_credential(self):
        """Test auth status with no stored credential."""
        mock_cred = CredentialResult(success=False, message="No credential")

        with patch("tp_mcp.tools.auth_status.get_credential", return_value=mock_cred):
            result = await tp_auth_status()

        assert result["valid"] is False
        assert result["athlete_id"] is None
        assert "tp-mcp auth" in result["action_needed"]

    @pytest.mark.asyncio
    async def test_expired_auth(self):
        """Test auth status with expired authentication."""
        mock_cred = CredentialResult(success=True, message="OK", cookie="test_cookie")
        mock_result = AuthResult(
            status=AuthStatus.EXPIRED,
            message="Session expired",
        )

        with patch("tp_mcp.tools.auth_status.get_credential", return_value=mock_cred):
            with patch(
                "tp_mcp.tools.auth_status.validate_auth",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                result = await tp_auth_status()

        assert result["valid"] is False
        assert "expired" in result["action_needed"].lower()
