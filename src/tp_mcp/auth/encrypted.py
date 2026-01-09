"""Encrypted file-based credential storage for TrainingPeaks authentication.

This is a fallback for environments where system keyring is not available
(headless servers, containers, etc.).
"""

import base64
import contextlib
import hashlib
import os
import platform
import stat
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from tp_mcp.auth.keyring import CredentialResult

# Storage location
CONFIG_DIR = Path.home() / ".config" / "trainingpeaks-mcp"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.enc"


def _get_machine_id() -> bytes:
    """Get a machine-specific identifier for key derivation.

    This combines several system identifiers to create a unique machine fingerprint.
    Not cryptographically secure on its own, but adds a layer of machine-binding.

    Returns:
        Machine identifier bytes.
    """
    components = [
        platform.node(),  # hostname
        platform.machine(),  # CPU architecture
        platform.system(),  # OS name
    ]

    # Try to get more stable machine identifiers
    try:
        # macOS: hardware UUID
        if platform.system() == "Darwin":
            import subprocess

            result = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if "IOPlatformUUID" in result.stdout:
                for line in result.stdout.split("\n"):
                    if "IOPlatformUUID" in line:
                        uuid = line.split("=")[-1].strip().strip('"')
                        components.append(uuid)
                        break
    except Exception:
        pass

    try:
        # Linux: machine-id
        machine_id_path = Path("/etc/machine-id")
        if machine_id_path.exists():
            components.append(machine_id_path.read_text().strip())
    except Exception:
        pass

    return "|".join(components).encode("utf-8")


def _derive_key(password: str | None = None) -> bytes:
    """Derive an encryption key from machine ID and optional password.

    Args:
        password: Optional user password for additional security.

    Returns:
        32-byte key for AES-256.
    """
    machine_id = _get_machine_id()
    salt = b"trainingpeaks-mcp-v1"

    key_material = machine_id + password.encode("utf-8") if password else machine_id

    # Use SHA-256 to derive a fixed-size key
    # In production, consider using PBKDF2 or Argon2 for password-based derivation
    return hashlib.sha256(salt + key_material).digest()


def _ensure_secure_directory() -> None:
    """Ensure the config directory exists with secure permissions."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Set directory permissions to 700 (owner only). Windows may not support chmod.
    with contextlib.suppress(OSError):
        os.chmod(CONFIG_DIR, stat.S_IRWXU)


def _set_file_permissions(path: Path) -> None:
    """Set secure file permissions (600 - owner read/write only)."""
    # Windows may not support chmod
    with contextlib.suppress(OSError):
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


class EncryptedCredentialStore:
    """Encrypted file-based credential storage.

    Uses AES-256-GCM for authenticated encryption with a key derived from
    machine-specific identifiers and an optional user password.
    """

    def __init__(self, password: str | None = None):
        """Initialize the encrypted credential store.

        Args:
            password: Optional password for additional security.
        """
        self._key = _derive_key(password)

    def store(self, cookie: str) -> CredentialResult:
        """Store the TrainingPeaks auth cookie in an encrypted file.

        Args:
            cookie: The Production_tpAuth cookie value.

        Returns:
            CredentialResult with success status.
        """
        if not cookie or not cookie.strip():
            return CredentialResult(success=False, message="Cookie value cannot be empty")

        try:
            _ensure_secure_directory()

            # Generate a random nonce (12 bytes for GCM)
            nonce = os.urandom(12)

            # Encrypt the cookie
            aesgcm = AESGCM(self._key)
            ciphertext = aesgcm.encrypt(nonce, cookie.strip().encode("utf-8"), None)

            # Store nonce + ciphertext, base64 encoded
            encrypted_data = base64.b64encode(nonce + ciphertext)
            CREDENTIALS_FILE.write_bytes(encrypted_data)

            _set_file_permissions(CREDENTIALS_FILE)

            return CredentialResult(success=True, message="Credential stored in encrypted file")

        except Exception as e:
            return CredentialResult(success=False, message=f"Encryption error: {e}")

    def get(self) -> CredentialResult:
        """Retrieve the TrainingPeaks auth cookie from the encrypted file.

        Returns:
            CredentialResult with cookie if found.
        """
        if not CREDENTIALS_FILE.exists():
            return CredentialResult(success=False, message="No credential file found")

        try:
            encrypted_data = base64.b64decode(CREDENTIALS_FILE.read_bytes())

            # Extract nonce and ciphertext
            nonce = encrypted_data[:12]
            ciphertext = encrypted_data[12:]

            # Decrypt
            aesgcm = AESGCM(self._key)
            cookie = aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")

            return CredentialResult(success=True, message="Credential retrieved", cookie=cookie)

        except Exception as e:
            return CredentialResult(
                success=False,
                message=f"Decryption error: {e}. File may be corrupted.",
            )

    def clear(self) -> CredentialResult:
        """Remove the encrypted credential file.

        Returns:
            CredentialResult with success status.
        """
        try:
            if CREDENTIALS_FILE.exists():
                CREDENTIALS_FILE.unlink()
            return CredentialResult(success=True, message="Credential file removed")
        except Exception as e:
            return CredentialResult(success=False, message=f"Error removing file: {e}")


# Module-level functions for consistency with keyring interface
_default_store: EncryptedCredentialStore | None = None


def _get_store() -> EncryptedCredentialStore:
    """Get or create the default encrypted store."""
    global _default_store
    if _default_store is None:
        _default_store = EncryptedCredentialStore()
    return _default_store


def store_credential_encrypted(cookie: str) -> CredentialResult:
    """Store credential using encrypted file storage."""
    return _get_store().store(cookie)


def get_credential_encrypted() -> CredentialResult:
    """Get credential from encrypted file storage."""
    return _get_store().get()


def clear_credential_encrypted() -> CredentialResult:
    """Clear credential from encrypted file storage."""
    return _get_store().clear()
