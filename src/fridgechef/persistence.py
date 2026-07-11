from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore, storage

from src.fridgechef.config import get_settings
from src.fridgechef.encryption import EncryptionService


def save_image_if_allowed(image_bytes: bytes, mime_type: str, allow_save: bool) -> str | None:
    """Persist an image only when both configuration and user consent allow it."""
    settings = get_settings()
    if not allow_save or not settings.allow_image_storage or not settings.bucket_name:
        return None

    extension = "jpg" if "jpeg" in mime_type or "jpg" in mime_type else "png"
    object_name = f"fridgechef/images/{uuid.uuid4().hex}.{extension}"

    bucket = storage.Client().bucket(settings.bucket_name)
    blob = bucket.blob(object_name)
    blob.upload_from_string(image_bytes, content_type=mime_type)

    return f"gs://{settings.bucket_name}/{object_name}"


def save_session_if_allowed(payload: dict[str, Any], allow_save: bool) -> str | None:
    """Persist a session only when both configuration and user consent allow it."""
    settings = get_settings()
    if not allow_save or not settings.allow_chat_persistence:
        return None

    encryption = EncryptionService(settings.encryption_key)
    session_id = uuid.uuid4().hex
    safe_payload = dict(payload)

    if "manual_ingredients" in safe_payload:
        raw_ingredients = str(safe_payload.pop("manual_ingredients"))
        safe_payload["manual_ingredients_encrypted"] = encryption.encrypt_text(raw_ingredients)

    safe_payload["created_at"] = datetime.now(timezone.utc).isoformat()
    firestore.Client().collection(settings.firestore_collection).document(session_id).set(safe_payload)

    return session_id
