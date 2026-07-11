from __future__ import annotations

import json
import re
import time
from pathlib import Path

VALID_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
SECRET_KEYS = {"private_key", "token", "refresh_token", "password", "client_secret"}


class CredentialError(Exception):
    """Raised when the local Google Cloud credentials file is missing or invalid."""


class ImageValidationError(Exception):
    """Raised when an uploaded image cannot be processed safely."""


def validate_service_account_json(path: str | Path) -> dict:
    """Validate the minimum structure required for a Google service account file."""
    credentials_path = Path(path)
    if not credentials_path.exists():
        raise CredentialError(f"No encuentro el archivo de credenciales: {credentials_path}")

    try:
        data = json.loads(credentials_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CredentialError("El archivo de credenciales no tiene formato JSON válido.") from exc

    required = {"type", "project_id", "client_email", "private_key"}
    missing = required - set(data)
    if missing:
        raise CredentialError(f"El archivo de credenciales no parece una service account. Faltan campos: {sorted(missing)}")
    if data.get("type") != "service_account":
        raise CredentialError("El archivo existe, pero no es de tipo service_account.")

    return data


def redact_sensitive(data):
    """Redact credentials before logging nested dictionaries or lists."""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            normalized_key = key.lower()
            if normalized_key in SECRET_KEYS or "token" in normalized_key or "key" in normalized_key:
                result[key] = "***REDACTED***"
            else:
                result[key] = redact_sensitive(value)
        return result

    if isinstance(data, list):
        return [redact_sensitive(item) for item in data]

    return data


def is_valid_email(email: str) -> bool:
    """Validate an email address for optional notifications."""
    return bool(email and EMAIL_RE.match(email.strip()))


def validate_image_upload(image_bytes: bytes, mime_type: str, max_mb: int) -> None:
    """Reject empty, unsupported or unexpectedly large images."""
    if not image_bytes:
        raise ImageValidationError("No he recibido ninguna imagen. Prueba a subirla de nuevo.")
    if mime_type not in VALID_IMAGE_MIME_TYPES:
        raise ImageValidationError("Este formato de imagen no es compatible. Usa JPG, PNG o WEBP.")

    max_bytes = max_mb * 1024 * 1024
    if len(image_bytes) > max_bytes:
        raise ImageValidationError(f"La imagen pesa demasiado. El máximo configurado es {max_mb} MB.")


def ensure_fresh_file(path: str | Path, started_at: float, max_stale_seconds: int) -> None:
    """Ensure a camera capture created a new file for the current request."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError("No se ha generado la foto esperada. Revisa que la cámara esté disponible.")

    modified_at = file_path.stat().st_mtime
    now = time.time()

    if modified_at < started_at:
        raise RuntimeError("La foto encontrada parece anterior a esta petición. Vuelve a intentarlo para evitar usar una imagen antigua.")
    if now - modified_at > max_stale_seconds:
        raise RuntimeError("La foto existe, pero parece demasiado antigua. Vuelve a tomarla antes de analizarla.")
