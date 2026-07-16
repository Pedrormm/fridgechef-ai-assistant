from __future__ import annotations

import base64

from src.fridgechef.mobile_upload import decode_mobile_upload_payload


def _payload(image_bytes: bytes = b"\xff\xd8\xff\xd9", mime_type: str = "image/jpeg") -> dict:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return {
        "dataUrl": f"data:{mime_type};base64,{encoded}",
        "uploadId": "upload-123",
        "filename": "nevera.jpg",
        "width": 1280,
        "height": 720,
        "originalSize": 2048,
    }


def test_decode_mobile_upload_payload_accepts_prepared_jpeg():
    result = decode_mobile_upload_payload(_payload(), max_bytes=1024)

    assert result is not None
    assert result.ok is True
    assert result.image_bytes == b"\xff\xd8\xff\xd9"
    assert result.mime_type == "image/jpeg"
    assert result.upload_id == "upload-123"
    assert result.filename == "nevera.jpg"
    assert result.width == 1280
    assert result.height == 720


def test_decode_mobile_upload_payload_normalises_jpeg_alias():
    result = decode_mobile_upload_payload(_payload(mime_type="image/jpg"), max_bytes=1024)

    assert result is not None
    assert result.ok is True
    assert result.mime_type == "image/jpeg"


def test_decode_mobile_upload_payload_rejects_oversized_result():
    result = decode_mobile_upload_payload(_payload(image_bytes=b"x" * 20), max_bytes=10)

    assert result is not None
    assert result.ok is False
    assert "demasiado grande" in result.error.lower()


def test_decode_mobile_upload_payload_preserves_friendly_frontend_error():
    result = decode_mobile_upload_payload(
        {
            "eventId": "failure-1",
            "filename": "foto.heic",
            "originalSize": 4096,
            "error": "Este formato no es compatible. Usa JPG, PNG o WEBP.",
        },
        max_bytes=1024,
    )

    assert result is not None
    assert result.ok is False
    assert result.upload_id == "failure-1"
    assert result.filename == "foto.heic"
    assert result.error == "Este formato no es compatible. Usa JPG, PNG o WEBP."


def test_decode_mobile_upload_payload_ignores_non_component_values():
    assert decode_mobile_upload_payload(None, max_bytes=1024) is None
    assert decode_mobile_upload_payload("not-a-payload", max_bytes=1024) is None
    assert decode_mobile_upload_payload({}, max_bytes=1024) is None
