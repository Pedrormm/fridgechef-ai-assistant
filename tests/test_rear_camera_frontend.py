from pathlib import Path


CAMERA_SCRIPT = Path("src/fridgechef/components/rear_camera/main.js")


def _camera_source() -> str:
    return CAMERA_SCRIPT.read_text(encoding="utf-8")


def test_camera_waits_until_the_streamlit_tab_is_visible():
    source = _camera_source()

    assert "function isComponentVisible()" in source
    assert "window.frameElement" in source
    assert "monitorVisibility();" in source
    assert 'setStatus("Abre esta pestaña para preparar la cámara.")' in source


def test_camera_requires_live_frames_before_enabling_capture():
    source = _camera_source()

    assert "function waitForLiveFrames" in source
    assert "requestVideoFrameCallback" in source
    assert "await waitForLiveFrames(video);" in source
    assert "captureButton.disabled = false;" in source


def test_camera_retries_one_failed_or_frozen_initial_stream():
    source = _camera_source()

    assert "retryCount < 1" in source
    assert "await startCamera(facingMode, retryCount + 1);" in source
    assert "stopActiveStream();" in source


def test_rear_camera_is_still_the_default_requested_mode():
    source = _camera_source()

    assert 'let desiredFacingMode = "environment";' in source
    assert 'componentArgs.preferredFacingMode === "user" ? "user" : "environment"' in source
