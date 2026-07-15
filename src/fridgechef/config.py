from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"

if load_dotenv and ENV_PATH.exists():
    load_dotenv(ENV_PATH)


def _bool(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable using common human-friendly values."""
    value = os.getenv(name, str(default)).strip().lower()
    return value in {"1", "true", "yes", "y", "on", "si", "sí"}


def _int(name: str, default: int) -> int:
    """Read an integer environment variable and keep a safe default on bad input."""
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _credential_path() -> Path:
    """Resolve credentials.json from either an absolute path or the project root."""
    raw = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json").strip() or "credentials.json"
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _project_id_from_credentials() -> str:
    """Use the explicit project id first, then fall back to credentials.json."""
    explicit = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID")
    if explicit:
        return explicit.strip()

    path = _credential_path()
    if not path.exists():
        return ""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return str(data.get("project_id", "")).strip()
    except Exception:
        return ""


@dataclass(frozen=True)
class Settings:
    """Central application settings loaded from .env and safe defaults."""

    app_name: str = os.getenv("APP_NAME", "FridgeChef_AI_PedroRamonMoreno")
    app_env: str = os.getenv("APP_ENV", "dev")
    credentials_path: str = str(_credential_path())
    project_id: str = _project_id_from_credentials()
    location: str = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    model_name: str = os.getenv("VERTEX_MODEL", "gemini-2.5-flash")
    image_location: str = (os.getenv("GOOGLE_CLOUD_IMAGE_LOCATION", "global") or "global").strip()
    recipe_image_provider: str = (os.getenv("RECIPE_IMAGE_PROVIDER", "gemini") or "gemini").strip().lower()
    image_model_name: str = (os.getenv("VERTEX_IMAGE_MODEL", "gemini-2.5-flash-image") or "gemini-2.5-flash-image").strip()
    imagen_model_name: str = (os.getenv("VERTEX_IMAGEN_MODEL", "imagen-4.0-generate-001") or "imagen-4.0-generate-001").strip()
    image_fallback_models: str = (os.getenv("VERTEX_IMAGE_FALLBACK_MODELS", "gemini-2.5-flash-image,imagen-4.0-generate-001,imagen-3.0-generate-002") or "").strip()
    image_aspect_ratio: str = (os.getenv("RECIPE_IMAGE_ASPECT_RATIO", "4:3") or "4:3").strip()
    image_size: str = (os.getenv("RECIPE_IMAGE_SIZE", "1K") or "1K").strip()
    image_output_mime_type: str = (os.getenv("RECIPE_IMAGE_OUTPUT_MIME_TYPE", "image/jpeg") or "image/jpeg").strip()
    image_debug: bool = _bool("RECIPE_IMAGE_DEBUG", False)
    recipe_images_enabled: bool = _bool("RECIPE_IMAGES_ENABLED", True)
    bucket_name: str = os.getenv("BUCKET_NAME", "")
    firestore_database: str = os.getenv("FIRESTORE_DATABASE", "(default)")
    firestore_collection: str = os.getenv("FIRESTORE_COLLECTION", "fridgechef_sessions")
    firestore_inventory_collection: str = os.getenv("FIRESTORE_INVENTORY_COLLECTION", "fridgechef_inventories")
    firestore_inventory_document: str = os.getenv("FIRESTORE_INVENTORY_DOCUMENT", "primary_inventory")
    persistence_backend: str = os.getenv("PERSISTENCE_BACKEND", "sqlite").strip().lower()
    local_database_path: str = os.getenv("LOCAL_DATABASE_PATH", "data/fridgechef.db")
    inventory_owner_id: str = os.getenv("INVENTORY_OWNER_ID", "default_user")
    allow_chat_persistence: bool = _bool("ALLOW_CHAT_PERSISTENCE", False)
    allow_image_storage: bool = _bool("ALLOW_IMAGE_STORAGE", False)
    encryption_enabled: bool = _bool("ENCRYPTION_ENABLED", True)
    encryption_key: str = os.getenv("FRIDGECHEF_MASTER_KEY") or os.getenv("APP_ENCRYPTION_KEY", "")
    max_image_mb: int = _int("MAX_IMAGE_MB", 10)
    mcp_enabled: bool = _bool("MCP_ENABLED", False)
    mcp_server_url: str = os.getenv("MCP_SERVER_URL", "http://localhost:8088/mcp")
    mcp_auth_token: str = os.getenv("MCP_AUTH_TOKEN", "")
    blink_enabled: bool = _bool("BLINK_ENABLED", False)
    blink_auth_file: str = os.getenv("BLINK_AUTH_FILE", "blink_auth.json")
    blink_output_file: str = os.getenv("BLINK_OUTPUT_FILE", "photos/blink_latest.jpg")
    blink_max_stale_seconds: int = _int("BLINK_MAX_STALE_SECONDS", _int("BLINK_MAX_PHOTO_AGE_SECONDS", 120))
    automation_enabled: bool = _bool("AUTOMATION_ENABLED", False)
    automation_engine: str = os.getenv("AUTOMATION_ENGINE", "python").lower().strip()
    automation_send_email: bool = _bool("AUTOMATION_SEND_EMAIL", False)
    automation_email_to: str = os.getenv("AUTOMATION_EMAIL_TO") or os.getenv("EMAIL_TO", "")
    email_enabled: bool = _bool("EMAIL_ENABLED", False)
    email_to: str = os.getenv("EMAIL_TO", "")
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = _int("SMTP_PORT", 587)
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from: str = os.getenv("SMTP_FROM", "")


def get_settings() -> Settings:
    """Return a fresh immutable settings object."""
    return Settings()
