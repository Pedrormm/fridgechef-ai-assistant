from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

try:
    from google.cloud import firestore, storage
except Exception:  # pragma: no cover - optional during local demos
    firestore = None
    storage = None

from src.fridgechef.config import get_settings
from src.fridgechef.encryption import EncryptionService

logger = logging.getLogger(__name__)


def save_image_if_allowed(image_bytes: bytes, mime_type: str, allow_save: bool) -> str | None:
    """Persist an image only when both configuration and user consent allow it.

    Cloud storage is useful, but it must never block a local demo. If Google
    Cloud is not configured, unavailable, or rejects the request, the app keeps
    working with the image already stored in the current Streamlit session.
    """
    settings = get_settings()
    if not allow_save or not settings.allow_image_storage or not settings.bucket_name:
        return None

    try:
        extension = "jpg" if "jpeg" in mime_type or "jpg" in mime_type else "png"
        object_name = f"fridgechef/images/{uuid.uuid4().hex}.{extension}"

        if storage is None:
            return None
        bucket = storage.Client().bucket(settings.bucket_name)
        blob = bucket.blob(object_name)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        return f"gs://{settings.bucket_name}/{object_name}"
    except Exception as exc:  # pragma: no cover - depends on external cloud services
        # Persistence is a secondary feature. The user action already succeeded
        # locally, so we log the cloud problem and keep the interface stable.
        logger.warning("Image persistence skipped: %s", exc)
        return None


def save_session_if_allowed(payload: dict[str, Any], allow_save: bool) -> str | None:
    """Persist a session only when both configuration and user consent allow it.

    Saving to Firestore is intentionally best-effort. A failed cloud write must
    not turn a successful fridge analysis into a red error in the web interface,
    especially during local tests where credentials, APIs or permissions may not
    be ready yet.
    """
    settings = get_settings()
    if not allow_save or not settings.allow_chat_persistence:
        return None

    try:
        encryption = EncryptionService(settings.encryption_key)
        session_id = uuid.uuid4().hex
        safe_payload = dict(payload)

        if "manual_ingredients" in safe_payload:
            raw_ingredients = str(safe_payload.pop("manual_ingredients"))
            safe_payload["manual_ingredients_encrypted"] = encryption.encrypt_text(raw_ingredients)

        safe_payload["created_at"] = datetime.now(timezone.utc).isoformat()
        if firestore is None:
            return None
        firestore.Client().collection(settings.firestore_collection).document(session_id).set(safe_payload)

        return session_id
    except Exception as exc:  # pragma: no cover - depends on external cloud services
        # Keep the local inventory and generated recipes available even when the
        # optional Firestore audit trail cannot be written.
        logger.warning("Session persistence skipped: %s", exc)
        return None
