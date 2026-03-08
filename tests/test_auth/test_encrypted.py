"""Tests for encrypted credential storage."""

import base64
import os

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from tp_mcp.auth.encrypted import (
    CREDENTIALS_FILE,
    EncryptedCredentialStore,
    _derive_key,
    _derive_key_legacy,
)


@pytest.fixture(autouse=True)
def _clean_credentials():
    """Remove credential file before and after each test."""
    CREDENTIALS_FILE.unlink(missing_ok=True)
    yield
    CREDENTIALS_FILE.unlink(missing_ok=True)


class TestDeriveKey:
    """Tests for the PBKDF2 key derivation function."""

    def test_returns_32_bytes(self):
        key = _derive_key()
        assert len(key) == 32

    def test_deterministic(self):
        key1 = _derive_key()
        key2 = _derive_key()
        assert key1 == key2

    def test_differs_with_password(self):
        key_no_pw = _derive_key()
        key_with_pw = _derive_key("mysecret")
        assert key_no_pw != key_with_pw

    def test_legacy_returns_32_bytes(self):
        key = _derive_key_legacy()
        assert len(key) == 32

    def test_new_key_differs_from_legacy(self):
        new_key = _derive_key()
        legacy_key = _derive_key_legacy()
        assert new_key != legacy_key


class TestEncryptedCredentialStore:
    """Tests for store/get/clear operations."""

    def test_store_and_retrieve_roundtrip(self):
        store = EncryptedCredentialStore()
        store.store("my-secret-cookie")
        result = store.get()
        assert result.success is True
        assert result.cookie == "my-secret-cookie"

    def test_store_and_retrieve_with_password(self):
        store = EncryptedCredentialStore(password="pw123")
        store.store("cookie-with-pw")
        result = store.get()
        assert result.success is True
        assert result.cookie == "cookie-with-pw"

    def test_legacy_migration(self):
        """Data encrypted with legacy key should be auto-migrated."""
        # Encrypt directly with the legacy key
        legacy_key = _derive_key_legacy()
        nonce = os.urandom(12)
        aesgcm = AESGCM(legacy_key)
        ciphertext = aesgcm.encrypt(nonce, b"legacy-cookie", None)
        CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        CREDENTIALS_FILE.write_bytes(base64.b64encode(nonce + ciphertext))

        # Retrieve via store (should fall back to legacy and migrate)
        store = EncryptedCredentialStore()
        result = store.get()
        assert result.success is True
        assert result.cookie == "legacy-cookie"
        assert "migrated" in result.message

        # Second retrieval should use new key directly
        result2 = store.get()
        assert result2.success is True
        assert result2.cookie == "legacy-cookie"
        assert result2.message == "Credential retrieved"

    def test_decryption_failure_returns_error(self):
        """Corrupted file should return a graceful error."""
        CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        CREDENTIALS_FILE.write_bytes(base64.b64encode(b"corrupted-data-here!!"))

        store = EncryptedCredentialStore()
        result = store.get()
        assert result.success is False
        assert "tp-mcp auth" in result.message

    def test_clear_nonexistent_file(self):
        """Clearing when no file exists should succeed."""
        store = EncryptedCredentialStore()
        result = store.clear()
        assert result.success is True

    def test_store_error_message_hides_details(self):
        """Error messages from store() should not leak exception details."""
        store = EncryptedCredentialStore()
        # Use an invalid key to force an encryption error
        store._key = b"short"  # Invalid AES key length
        result = store.store("some-cookie")
        assert result.success is False
        assert "Encryption error" in result.message
        # Should contain only the exception type, not the full message
        assert "(" in result.message
