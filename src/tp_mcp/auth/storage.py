"""Unified credential storage with automatic backend selection.

Uses system keyring when available, falls back to encrypted file storage.
Environment variable override is also supported for CI/testing.
"""

import os

from tp_mcp.auth.encrypted import (
    clear_credential_encrypted,
    get_credential_encrypted,
    store_credential_encrypted,
)
from tp_mcp.auth.keyring import (
    CredentialResult,
    clear_credential as clear_credential_keyring,
    get_credential as get_credential_keyring,
    is_keyring_available,
    store_credential as store_credential_keyring,
)

ENV_VAR_NAME = "TP_AUTH_COOKIE"


def get_storage_backend() -> str:
    """Get the current storage backend name.

    Returns:
        Name of the storage backend being used.
    """
    if os.environ.get(ENV_VAR_NAME):
        return "environment"
    if is_keyring_available():
        return "keyring"
    return "encrypted_file"


def store_credential(cookie: str) -> CredentialResult:
    """Store the TrainingPeaks auth cookie.

    Always stores in encrypted file for reliability. Also stores in keyring
    if available (but keyring access can be blocked by app-specific permissions
    on macOS when spawned from different applications like Claude Desktop).

    Args:
        cookie: The Production_tpAuth cookie value.

    Returns:
        CredentialResult with success status.
    """
    # Always store in encrypted file first (reliable fallback)
    encrypted_result = store_credential_encrypted(cookie)

    # Also try keyring if available (may fail due to app permissions)
    if is_keyring_available():
        keyring_result = store_credential_keyring(cookie)
        if keyring_result.success:
            return CredentialResult(
                success=True,
                message="Credential stored in keyring and encrypted file",
            )

    return encrypted_result


def get_credential() -> CredentialResult:
    """Retrieve the TrainingPeaks auth cookie.

    Checks in order:
    1. Environment variable (for CI/testing)
    2. System keyring
    3. Encrypted file

    Returns:
        CredentialResult with cookie if found.
    """
    # Check environment variable first (CI/testing override)
    env_cookie = os.environ.get(ENV_VAR_NAME)
    if env_cookie:
        return CredentialResult(
            success=True,
            message="Credential from environment variable",
            cookie=env_cookie,
        )

    # Try keyring first
    if is_keyring_available():
        result = get_credential_keyring()
        if result.success:
            return result

    # Fall back to encrypted file
    return get_credential_encrypted()


def clear_credential() -> CredentialResult:
    """Clear stored credentials from all backends.

    Returns:
        CredentialResult with success status.
    """
    results = []

    # Clear from keyring
    if is_keyring_available():
        results.append(clear_credential_keyring())

    # Clear from encrypted file
    results.append(clear_credential_encrypted())

    # Return success if any succeeded
    if any(r.success for r in results):
        return CredentialResult(success=True, message="Credentials cleared")

    return CredentialResult(success=False, message="No credentials to clear")
