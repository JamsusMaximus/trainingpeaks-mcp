"""Tests for keyring credential storage."""

from unittest.mock import MagicMock, patch

from tp_mcp.auth.keyring import (
    clear_credential,
    get_credential,
    is_keyring_available,
    store_credential,
)


class TestIsKeyringAvailable:
    """Tests for is_keyring_available function."""

    def test_available_with_real_backend(self):
        """Test returns True when a real keyring backend is available."""
        with patch("tp_mcp.auth.keyring.keyring") as mock:
            mock.get_keyring.return_value = MagicMock(__class__=type("RealKeyring", (), {}))
            assert is_keyring_available() is True

    def test_unavailable_with_fail_backend(self):
        """Test returns False when only fail backend is available."""
        with patch("tp_mcp.auth.keyring.keyring") as mock:
            # Create a mock that reports as a Fail backend
            fail_backend = MagicMock()
            fail_backend.__class__.__name__ = "FailKeyring"
            mock.get_keyring.return_value = fail_backend
            assert is_keyring_available() is False


class TestStoreCredential:
    """Tests for store_credential function."""

    def test_store_success(self, mock_keyring):
        """Test successful credential storage."""
        result = store_credential("test_cookie")
        assert result.success is True
        assert "stored" in result.message.lower()

    def test_store_empty_cookie(self, mock_keyring):
        """Test storing empty cookie fails."""
        result = store_credential("")
        assert result.success is False
        assert "empty" in result.message.lower()

    def test_store_whitespace_cookie(self, mock_keyring):
        """Test storing whitespace-only cookie fails."""
        result = store_credential("   ")
        assert result.success is False


class TestGetCredential:
    """Tests for get_credential function."""

    def test_get_existing_credential(self, mock_keyring):
        """Test retrieving existing credential."""
        # First store a credential
        store_credential("test_cookie")
        result = get_credential()
        assert result.success is True
        assert result.cookie == "test_cookie"

    def test_get_nonexistent_credential(self, mock_keyring):
        """Test retrieving non-existent credential."""
        result = get_credential()
        assert result.success is False
        assert result.cookie is None


class TestClearCredential:
    """Tests for clear_credential function."""

    def test_clear_existing_credential(self, mock_keyring):
        """Test clearing existing credential."""
        store_credential("test_cookie")
        result = clear_credential()
        assert result.success is True

        # Verify it's gone
        get_result = get_credential()
        assert get_result.success is False

    def test_clear_nonexistent_credential(self, mock_keyring):
        """Test clearing non-existent credential succeeds."""
        result = clear_credential()
        assert result.success is True
