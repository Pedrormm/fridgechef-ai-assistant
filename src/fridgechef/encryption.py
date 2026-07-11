from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class EncryptionService:
    """Optional text encryption wrapper used before storing sensitive session fields."""

    def __init__(self, key: str | None):
        self.key = key or ""
        self._fernet = Fernet(self.key.encode("utf-8")) if self.key else None

    @staticmethod
    def generate_key() -> str:
        """Generate a stable key that can be stored outside the repository."""
        return Fernet.generate_key().decode("utf-8")

    def encrypt_text(self, text: str) -> str:
        """Encrypt text when encryption is configured; otherwise return it unchanged."""
        if not self._fernet or text is None:
            return text
        return self._fernet.encrypt(text.encode("utf-8")).decode("utf-8")

    def decrypt_text(self, token: str) -> str:
        """Decrypt text and fail open for old plaintext values."""
        if not self._fernet or token is None:
            return token
        try:
            return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            return token
