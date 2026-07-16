from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any


_SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MIME_ALIASES = {
    "image/jpg": "image/jpeg",
    "image/pjpeg": "image/jpeg",
    "image/x-png": "image/png",
}
_EXTENSION_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_GENERIC_BROWSER_MIME_TYPES = {"", "application/octet-stream", "binary/octet-stream"}


@dataclass(frozen=True)
class UploadedImageInput:
    """Normalized image data read from a Streamlit uploaded file object."""

    image_bytes: bytes
    mime_type: str
    filename: str
    upload_id: str


def _normalise_declared_mime_type(value: object) -> str:
    """Return a lowercase canonical browser MIME value."""
    declared = str(value or "").strip().lower()
    return _MIME_ALIASES.get(declared, declared)


def _mime_type_from_extension(filename: str) -> str:
    """Resolve supported image extensions without relying on OS MIME tables."""
    clean_name = str(filename or "").split("?", 1)[0].split("#", 1)[0]
    suffix = PurePath(clean_name).suffix.lower()
    return _EXTENSION_MIME_TYPES.get(suffix, "")


def normalize_image_mime_type(filename: str, declared_mime_type: object) -> str:
    """Return a supported MIME type consistently across browsers and Docker.

    Browser upload controls may send an empty or generic MIME value. Python's
    ``mimetypes`` database also varies between operating systems, so the supported
    image extensions are resolved from an application-owned mapping first. The OS
    database remains only a final compatibility fallback for known image types.
    """
    declared = _normalise_declared_mime_type(declared_mime_type)
    if declared in _SUPPORTED_IMAGE_TYPES:
        return declared

    extension_type = _mime_type_from_extension(filename)
    if extension_type:
        return extension_type

    guessed = (mimetypes.guess_type(filename or "", strict=False)[0] or "").lower()
    guessed = _MIME_ALIASES.get(guessed, guessed)
    if guessed in _SUPPORTED_IMAGE_TYPES:
        return guessed

    if declared not in _GENERIC_BROWSER_MIME_TYPES:
        return declared
    return "application/octet-stream"


def uploaded_file_identifier(uploaded_file: Any, image_bytes: bytes) -> str:
    """Create a stable identifier while preferring Streamlit's upload file ID."""
    file_id = str(getattr(uploaded_file, "file_id", "") or "").strip()
    if file_id:
        return f"streamlit:{file_id}"
    digest = hashlib.sha256(image_bytes).hexdigest()
    filename = str(getattr(uploaded_file, "name", "") or "").strip()
    return f"sha256:{digest}:{filename}"


def read_uploaded_image(uploaded_file: Any) -> UploadedImageInput | None:
    """Read one uploaded file without depending on a concrete Streamlit class."""
    if uploaded_file is None:
        return None

    getter = getattr(uploaded_file, "getvalue", None)
    if not callable(getter):
        raise TypeError("The uploaded file does not provide binary data.")

    image_bytes = bytes(getter())
    filename = str(getattr(uploaded_file, "name", "") or "uploaded-image").strip()
    mime_type = normalize_image_mime_type(
        filename,
        getattr(uploaded_file, "type", ""),
    )
    return UploadedImageInput(
        image_bytes=image_bytes,
        mime_type=mime_type,
        filename=filename,
        upload_id=uploaded_file_identifier(uploaded_file, image_bytes),
    )
