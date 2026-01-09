"""Tests for cookie validation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tp_mcp.auth.validator import AuthStatus, validate_auth


class TestValidateAuth:
    """Tests for validate_auth function."""

    @pytest.mark.asyncio
    async def test_valid_auth(self):
        """Test validation with valid cookie."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "athleteId": 123,
            "userId": 456,
            "username": "test@example.com",
        }

        with patch("tp_mcp.auth.validator.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await validate_auth("valid_cookie")

            assert result.is_valid is True
            assert result.status == AuthStatus.VALID
            assert result.athlete_id == 123
            assert result.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_expired_auth(self):
        """Test validation with expired cookie."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("tp_mcp.auth.validator.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await validate_auth("expired_cookie")

            assert result.is_valid is False
            assert result.status == AuthStatus.EXPIRED

    @pytest.mark.asyncio
    async def test_invalid_auth(self):
        """Test validation with invalid cookie."""
        mock_response = MagicMock()
        mock_response.status_code = 403

        with patch("tp_mcp.auth.validator.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await validate_auth("invalid_cookie")

            assert result.is_valid is False
            assert result.status == AuthStatus.INVALID

    @pytest.mark.asyncio
    async def test_empty_cookie(self):
        """Test validation with empty cookie."""
        result = await validate_auth("")
        assert result.is_valid is False
        assert result.status == AuthStatus.NO_CREDENTIAL

    @pytest.mark.asyncio
    async def test_network_error(self):
        """Test validation with network error."""
        import httpx

        with patch("tp_mcp.auth.validator.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.side_effect = httpx.RequestError("Network error")
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await validate_auth("some_cookie")

            assert result.is_valid is False
            assert result.status == AuthStatus.NETWORK_ERROR
