import base64
from pathlib import Path

from src.fridgechef.device_camera import decode_camera_payload


def _payload(raw: bytes = b"jpeg-bytes", **overrides):
    encoded = base64.b64encode(raw).decode("ascii")
    payload = {
        "dataUrl": f"data:image/jpeg;base64,{encoded}",
        "captureId": "capture-1",
        "width": 1280,
        "height": 720,
        "facingMode": "environment",
    }
    payload.update(overrides)
    return payload


def test_decode_camera_payload_preserves_rear_camera_metadata():
    capture = decode_camera_payload(_payload(), max_bytes=1024)

    assert capture is not None
    assert capture.image_bytes == b"jpeg-bytes"
    assert capture.mime_type == "image/jpeg"
    assert capture.capture_id == "capture-1"
    assert capture.width == 1280
    assert capture.height == 720
    assert capture.facing_mode == "environment"


def test_decode_camera_payload_rejects_invalid_or_oversized_images():
    assert decode_camera_payload(None, max_bytes=1024) is None
    assert decode_camera_payload({"dataUrl": "invalid", "captureId": "x"}, max_bytes=1024) is None
    assert decode_camera_payload(_payload(b"too-large"), max_bytes=3) is None


def test_rear_camera_frontend_requests_environment_facing_mode_first():
    frontend = Path("src/fridgechef/components/rear_camera/main.js").read_text(encoding="utf-8")

    assert 'activeFacingMode = "environment"' in frontend
    assert 'preferredFacingMode === "user" ? "user" : "environment"' in frontend
    assert "facingMode: facingConstraint" in frontend
    assert "cameraConstraints(facingMode, true)" in frontend
    assert "cameraConstraints(facingMode, false)" in frontend
