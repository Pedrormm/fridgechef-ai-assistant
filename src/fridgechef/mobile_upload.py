from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import streamlit.components.v1 as components
except Exception:  # pragma: no cover - allows pure unit tests without Streamlit
    components = None


_FRONTEND_DIR = Path(__file__).resolve().parent / "components" / "mobile_upload"
_MOBILE_UPLOAD_COMPONENT = (
    components.declare_component(
        "fridgechef_mobile_upload",
        path=str(_FRONTEND_DIR),
    )
    if components is not None
    else None
)
_SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MIME_ALIASES = {"image/jpg": "image/jpeg", "image/pjpeg": "image/jpeg"}


@dataclass(frozen=True)
class MobileUploadResult:
    """One image prepared by the browser before it reaches Streamlit."""

    image_bytes: bytes | None
    mime_type: str
    upload_id: str
    filename: str
    width: int | None = None
    height: int | None = None
    original_size: int | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        """Return whether the payload contains a valid prepared image."""
        return bool(self.image_bytes and not self.error)


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def decode_mobile_upload_payload(payload: Any, max_bytes: int) -> MobileUploadResult | None:
    """Validate and decode the payload returned by the mobile upload component."""
    if not isinstance(payload, dict):
        return None

    upload_id = str(payload.get("uploadId") or payload.get("eventId") or "").strip()
    filename = str(payload.get("filename") or "foto.jpg").strip() or "foto.jpg"
    error = str(payload.get("error") or "").strip()
    if error:
        return MobileUploadResult(
            image_bytes=None,
            mime_type="",
            upload_id=upload_id,
            filename=filename,
            original_size=_positive_int(payload.get("originalSize")),
            error=error,
        )

    data_url = payload.get("dataUrl")
    if not isinstance(data_url, str) or not data_url.startswith("data:image/") or not upload_id:
        return None

    try:
        header, encoded = data_url.split(",", 1)
        mime_type = header[5:].split(";", 1)[0].lower()
        mime_type = _MIME_ALIASES.get(mime_type, mime_type)
        if mime_type not in _SUPPORTED_IMAGE_TYPES:
            return MobileUploadResult(
                image_bytes=None,
                mime_type=mime_type,
                upload_id=upload_id,
                filename=filename,
                error="Este formato de imagen no es compatible. Usa JPG, PNG o WEBP.",
            )
        image_bytes = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        return MobileUploadResult(
            image_bytes=None,
            mime_type="",
            upload_id=upload_id,
            filename=filename,
            error="No he podido leer esta foto. Selecciónala de nuevo o prueba con otra imagen.",
        )

    if not image_bytes:
        return MobileUploadResult(
            image_bytes=None,
            mime_type=mime_type,
            upload_id=upload_id,
            filename=filename,
            error="La foto está vacía. Selecciona otra imagen.",
        )
    if len(image_bytes) > max(1, int(max_bytes)):
        return MobileUploadResult(
            image_bytes=None,
            mime_type=mime_type,
            upload_id=upload_id,
            filename=filename,
            error="La foto preparada sigue siendo demasiado grande. Prueba con otra imagen.",
        )

    return MobileUploadResult(
        image_bytes=image_bytes,
        mime_type=mime_type,
        upload_id=upload_id,
        filename=filename,
        width=_positive_int(payload.get("width")),
        height=_positive_int(payload.get("height")),
        original_size=_positive_int(payload.get("originalSize")),
    )


def mobile_image_upload(
    *,
    key: str,
    max_source_mb: int = 25,
    max_output_mb: int = 3,
    max_dimension: int = 1920,
    select_label: str = "Seleccionar foto",
    processing_label: str = "Preparando la foto…",
    ready_label: str = "Foto preparada. Ya puedes analizarla.",
    unsupported_label: str = "Este formato no es compatible. Usa JPG, PNG o WEBP.",
    too_large_label: str = "La foto es demasiado grande para prepararla.",
    failed_label: str = "No he podido preparar esta foto. Prueba con otra imagen.",
) -> MobileUploadResult | None:
    """Render a mobile-friendly gallery picker with browser-side image resizing."""
    if _MOBILE_UPLOAD_COMPONENT is None:
        raise RuntimeError("Streamlit is required to render the mobile upload component.")

    output_limit = max(1, int(max_output_mb)) * 1024 * 1024
    payload = _MOBILE_UPLOAD_COMPONENT(
        accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp",
        maxSourceBytes=max(1, int(max_source_mb)) * 1024 * 1024,
        maxOutputBytes=output_limit,
        maxDimension=max(320, int(max_dimension)),
        selectLabel=select_label,
        processingLabel=processing_label,
        readyLabel=ready_label,
        unsupportedLabel=unsupported_label,
        tooLargeLabel=too_large_label,
        failedLabel=failed_label,
        key=key,
        default=None,
    )
    return decode_mobile_upload_payload(payload, max_bytes=output_limit)
