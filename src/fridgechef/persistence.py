from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from google.cloud import firestore, storage
    from google.oauth2 import service_account
except Exception:  # pragma: no cover - dependencias opcionales en demos locales
    firestore = None
    storage = None
    service_account = None

from src.fridgechef.config import get_settings
from src.fridgechef.encryption import EncryptionService

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SQLITE_LOCK = threading.Lock()


@dataclass(frozen=True)
class InventoryPersistenceResult:
    """Resultado de cargar, guardar o borrar el inventario persistente."""

    inventory: list[dict[str, Any]]
    backend: str
    success: bool
    updated_at: str | None = None
    warning: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise_backend(value: str) -> str:
    backend = (value or "auto").strip().lower()
    return backend if backend in {"auto", "sqlite", "firestore"} else "auto"


def _database_path(settings: Any) -> Path:
    path = Path(settings.local_database_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _open_sqlite(settings: Any) -> sqlite3.Connection:
    path = _database_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_state (
            owner_id TEXT PRIMARY KEY,
            inventory_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def _load_sqlite(settings: Any) -> tuple[list[dict[str, Any]], str | None]:
    with _SQLITE_LOCK:
        with _open_sqlite(settings) as connection:
            row = connection.execute(
                "SELECT inventory_json, updated_at FROM inventory_state WHERE owner_id = ?",
                (settings.inventory_owner_id,),
            ).fetchone()

    if not row:
        return [], None

    payload = json.loads(row[0])
    if not isinstance(payload, list):
        return [], row[1]
    return [item for item in payload if isinstance(item, dict)], row[1]


def _save_sqlite(settings: Any, inventory: list[dict[str, Any]], updated_at: str) -> None:
    serialised = json.dumps(inventory, ensure_ascii=False)
    with _SQLITE_LOCK:
        with _open_sqlite(settings) as connection:
            connection.execute(
                """
                INSERT INTO inventory_state (owner_id, inventory_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(owner_id) DO UPDATE SET
                    inventory_json = excluded.inventory_json,
                    updated_at = excluded.updated_at
                """,
                (settings.inventory_owner_id, serialised, updated_at),
            )
            connection.commit()


def _clear_sqlite(settings: Any) -> None:
    with _SQLITE_LOCK:
        with _open_sqlite(settings) as connection:
            connection.execute(
                "DELETE FROM inventory_state WHERE owner_id = ?",
                (settings.inventory_owner_id,),
            )
            connection.commit()


def _firestore_client(settings: Any):
    """Crear el cliente con credentials.json directamente, sin depender de gcloud."""
    if firestore is None:
        raise RuntimeError("La librería de Firestore no está instalada")

    client_kwargs: dict[str, Any] = {}
    if settings.project_id:
        client_kwargs["project"] = settings.project_id

    credentials_path = Path(settings.credentials_path)
    if credentials_path.exists() and service_account is not None:
        credentials = service_account.Credentials.from_service_account_file(str(credentials_path))
        client_kwargs["credentials"] = credentials

    database = (settings.firestore_database or "(default)").strip()
    try:
        return firestore.Client(database=database, **client_kwargs)
    except TypeError:  # compatibilidad con versiones antiguas del cliente
        return firestore.Client(**client_kwargs)


def _inventory_document(settings: Any):
    client = _firestore_client(settings)
    return client.collection(settings.firestore_inventory_collection).document(
        settings.firestore_inventory_document
    )


def _load_firestore(settings: Any) -> tuple[list[dict[str, Any]], str | None]:
    snapshot = _inventory_document(settings).get()
    if not snapshot.exists:
        return [], None

    data = snapshot.to_dict() or {}
    inventory = data.get("inventory", [])
    updated_at = data.get("updated_at")
    if not isinstance(inventory, list):
        inventory = []
    return [item for item in inventory if isinstance(item, dict)], str(updated_at) if updated_at else None


def _save_firestore(settings: Any, inventory: list[dict[str, Any]], updated_at: str) -> None:
    _inventory_document(settings).set(
        {
            "owner_id": settings.inventory_owner_id,
            "inventory": inventory,
            "updated_at": updated_at,
        }
    )


def _clear_firestore(settings: Any) -> None:
    _inventory_document(settings).delete()


def _timestamp_value(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def load_inventory_state() -> InventoryPersistenceResult:
    """Cargar el inventario más reciente de Firestore o de SQLite local.

    En modo ``auto`` se consultan ambos almacenes y se usa la versión más
    reciente. SQLite garantiza persistencia inmediata en localhost incluso si
    Firestore todavía no existe o la cuenta de servicio no tiene permisos.
    """
    settings = get_settings()
    if not settings.allow_chat_persistence:
        return InventoryPersistenceResult([], "disabled", True)

    backend = _normalise_backend(settings.persistence_backend)
    candidates: list[tuple[str, list[dict[str, Any]], str | None]] = []
    warnings: list[str] = []

    if backend in {"auto", "sqlite"}:
        try:
            inventory, updated_at = _load_sqlite(settings)
            candidates.append(("sqlite", inventory, updated_at))
        except Exception as exc:
            logger.warning("No se pudo leer SQLite: %s", exc)
            warnings.append("No se pudo leer la base de datos local")

    if backend in {"auto", "firestore"}:
        try:
            inventory, updated_at = _load_firestore(settings)
            candidates.append(("firestore", inventory, updated_at))
        except Exception as exc:  # pragma: no cover - depende de Google Cloud
            logger.warning("No se pudo leer Firestore: %s", exc)
            warnings.append("Firestore no está disponible")

    if not candidates:
        return InventoryPersistenceResult([], "none", False, warning="; ".join(warnings) or None)

    selected = max(candidates, key=lambda item: _timestamp_value(item[2]))
    active_backends = "+".join(item[0] for item in candidates)
    return InventoryPersistenceResult(
        selected[1],
        active_backends,
        True,
        selected[2],
        "; ".join(warnings) or None,
    )


def save_inventory_state(inventory: list[dict[str, Any]]) -> InventoryPersistenceResult:
    """Guardar el estado completo de la nevera con un identificador estable."""
    settings = get_settings()
    if not settings.allow_chat_persistence:
        return InventoryPersistenceResult(inventory, "disabled", True)

    backend = _normalise_backend(settings.persistence_backend)
    updated_at = _utc_now()
    saved_backends: list[str] = []
    warnings: list[str] = []

    if backend in {"auto", "sqlite"}:
        try:
            _save_sqlite(settings, inventory, updated_at)
            saved_backends.append("sqlite")
        except Exception as exc:
            logger.exception("No se pudo guardar el inventario en SQLite: %s", exc)
            warnings.append("No se pudo guardar en la base de datos local")

    if backend in {"auto", "firestore"}:
        try:
            _save_firestore(settings, inventory, updated_at)
            saved_backends.append("firestore")
        except Exception as exc:  # pragma: no cover - depende de Google Cloud
            logger.warning("No se pudo guardar el inventario en Firestore: %s", exc)
            warnings.append("Firestore no está disponible")

    return InventoryPersistenceResult(
        inventory,
        "+".join(saved_backends) if saved_backends else "none",
        bool(saved_backends),
        updated_at,
        "; ".join(warnings) or None,
    )


def clear_inventory_state() -> InventoryPersistenceResult:
    """Borrar de forma persistente el inventario guardado."""
    settings = get_settings()
    if not settings.allow_chat_persistence:
        return InventoryPersistenceResult([], "disabled", True)

    backend = _normalise_backend(settings.persistence_backend)
    cleared_backends: list[str] = []
    warnings: list[str] = []

    if backend in {"auto", "sqlite"}:
        try:
            _clear_sqlite(settings)
            cleared_backends.append("sqlite")
        except Exception as exc:
            logger.exception("No se pudo borrar el inventario de SQLite: %s", exc)
            warnings.append("No se pudo borrar de la base de datos local")

    if backend in {"auto", "firestore"}:
        try:
            _clear_firestore(settings)
            cleared_backends.append("firestore")
        except Exception as exc:  # pragma: no cover - depende de Google Cloud
            logger.warning("No se pudo borrar el inventario de Firestore: %s", exc)
            warnings.append("Firestore no está disponible")

    return InventoryPersistenceResult(
        [],
        "+".join(cleared_backends) if cleared_backends else "none",
        bool(cleared_backends),
        _utc_now(),
        "; ".join(warnings) or None,
    )


def save_image_if_allowed(image_bytes: bytes, mime_type: str, allow_save: bool) -> str | None:
    """Guardar una imagen únicamente cuando configuración y consentimiento lo permiten."""
    settings = get_settings()
    if not allow_save or not settings.allow_image_storage or not settings.bucket_name:
        return None

    try:
        extension = "jpg" if "jpeg" in mime_type or "jpg" in mime_type else "png"
        object_name = f"fridgechef/images/{uuid.uuid4().hex}.{extension}"

        if storage is None:
            return None
        credentials_path = Path(settings.credentials_path)
        client_kwargs: dict[str, Any] = {"project": settings.project_id} if settings.project_id else {}
        if credentials_path.exists() and service_account is not None:
            client_kwargs["credentials"] = service_account.Credentials.from_service_account_file(
                str(credentials_path)
            )
        bucket = storage.Client(**client_kwargs).bucket(settings.bucket_name)
        blob = bucket.blob(object_name)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        return f"gs://{settings.bucket_name}/{object_name}"
    except Exception as exc:  # pragma: no cover - depende de servicios externos
        logger.warning("No se pudo guardar la imagen: %s", exc)
        return None


def save_session_if_allowed(payload: dict[str, Any], allow_save: bool) -> str | None:
    """Guardar un evento histórico en Firestore sin bloquear la aplicación."""
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

        safe_payload["created_at"] = _utc_now()
        _firestore_client(settings).collection(settings.firestore_collection).document(session_id).set(
            safe_payload
        )
        return session_id
    except Exception as exc:  # pragma: no cover - depende de Google Cloud
        logger.warning("No se pudo guardar el evento de sesión: %s", exc)
        return None
