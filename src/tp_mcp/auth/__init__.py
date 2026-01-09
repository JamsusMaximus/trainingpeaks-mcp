"""Authentication module for TrainingPeaks MCP Server."""

from tp_mcp.auth.encrypted import EncryptedCredentialStore
from tp_mcp.auth.keyring import CredentialResult, is_keyring_available
from tp_mcp.auth.storage import (
    clear_credential,
    get_credential,
    get_storage_backend,
    store_credential,
)
from tp_mcp.auth.validator import AuthResult, AuthStatus, validate_auth, validate_auth_sync

__all__ = [
    "AuthResult",
    "AuthStatus",
    "CredentialResult",
    "EncryptedCredentialStore",
    "clear_credential",
    "get_credential",
    "get_storage_backend",
    "is_keyring_available",
    "store_credential",
    "validate_auth",
    "validate_auth_sync",
]
