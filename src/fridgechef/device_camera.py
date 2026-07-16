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


_FRONTEND_DIR = Path(__file__).resolve().parent / "components" / "rear_camera"
_REAR_CAMERA_COMPONENT = (
    components.declare_component(
        "fridgechef_rear_camera",
        path=str(_FRONTEND_DIR),
    )
    if components is not None
    else None
)
_SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


@dataclass(frozen=True)
class DeviceCameraCapture:
    """One image captured by the browser camera component."""

    image_bytes: bytes
    mime_type: str
    capture_id: str
    width: int | None = None
    height: int | None = None
    facing_mode: str = "environment"


def decode_camera_payload(payload: Any, max_bytes: int) -> DeviceCameraCapture | None:
    """Validate and decode the data URL returned by the browser component."""
    if not isinstance(payload, dict):
        return None

    data_url = payload.get("dataUrl")
    capture_id = str(payload.get("captureId") or "").strip()
    if not isinstance(data_url, str) or not data_url.startswith("data:image/") or not capture_id:
        return None

    try:
        header, encoded = data_url.split(",", 1)
        mime_type = header[5:].split(";", 1)[0].lower()
        if mime_type not in _SUPPORTED_IMAGE_TYPES:
            return None
        image_bytes = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        return None

    if not image_bytes or len(image_bytes) > max(1, int(max_bytes)):
        return None

    def _positive_int(value: Any) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    facing_mode = str(payload.get("facingMode") or "environment").strip().lower()
    if facing_mode not in {"environment", "user"}:
        facing_mode = "environment"

    return DeviceCameraCapture(
        image_bytes=image_bytes,
        mime_type=mime_type,
        capture_id=capture_id,
        width=_positive_int(payload.get("width")),
        height=_positive_int(payload.get("height")),
        facing_mode=facing_mode,
    )


def rear_camera_input(
    *,
    key: str,
    max_image_mb: int = 10,
    preferred_facing_mode: str = "environment",
    capture_label: str = "Hacer foto",
    switch_label: str = "Cambiar cámara",
    starting_label: str = "Abriendo la cámara trasera…",
) -> DeviceCameraCapture | None:
    """Render a browser camera that requests the rear-facing lens first."""
    if _REAR_CAMERA_COMPONENT is None:
        raise RuntimeError("Streamlit is required to render the device camera component.")

    facing_mode = preferred_facing_mode if preferred_facing_mode in {"environment", "user"} else "environment"
    payload = _REAR_CAMERA_COMPONENT(
        preferredFacingMode=facing_mode,
        captureLabel=capture_label,
        switchLabel=switch_label,
        startingLabel=starting_label,
        key=key,
        default=None,
    )
    return decode_camera_payload(payload, max_bytes=max_image_mb * 1024 * 1024)
