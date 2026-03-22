"""Encryption utilities for data at rest and sensitive fields."""

from __future__ import annotations

import base64
import hashlib
import os

import structlog
from cryptography.fernet import Fernet

logger = structlog.get_logger(__name__)


class FieldEncryptor:
    """Encrypt/decrypt sensitive fields (integration configs, API keys, etc.).

    Uses Fernet (AES-128-CBC + HMAC-SHA256) from the ``cryptography`` library
    which is already available via the ``PyJWT[crypto]`` dependency.
    """

    def __init__(self, master_key: str = "") -> None:
        if not master_key:
            master_key = os.environ.get("RAYOLLY_ENCRYPTION_KEY", "")
        if not master_key:
            # Generate a deterministic dev key — NOT for production
            master_key = base64.urlsafe_b64encode(
                hashlib.sha256(b"rayolly-dev-key").digest()
            ).decode()
            logger.warning("encryption.using_dev_key")

        self._fernet = Fernet(self._ensure_valid_key(master_key))

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string, return base64-encoded ciphertext."""
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt base64-encoded ciphertext."""
        return self._fernet.decrypt(ciphertext.encode()).decode()

    def encrypt_dict(self, data: dict, fields: list[str]) -> dict:
        """Encrypt specific fields in a dictionary."""
        result = dict(data)
        for field_name in fields:
            if field_name in result and result[field_name]:
                result[field_name] = self.encrypt(str(result[field_name]))
        return result

    def decrypt_dict(self, data: dict, fields: list[str]) -> dict:
        """Decrypt specific fields in a dictionary."""
        result = dict(data)
        for field_name in fields:
            if field_name in result and result[field_name]:
                try:
                    result[field_name] = self.decrypt(str(result[field_name]))
                except Exception:
                    pass  # Field may not be encrypted
        return result

    @staticmethod
    def _ensure_valid_key(key: str) -> bytes:
        """Ensure the key is valid Fernet format (32 url-safe base64 bytes)."""
        try:
            decoded = base64.urlsafe_b64decode(key)
            if len(decoded) == 32:
                return key.encode()
        except Exception:
            pass
        # Derive a valid key from whatever was provided
        derived = hashlib.sha256(key.encode()).digest()
        return base64.urlsafe_b64encode(derived)
