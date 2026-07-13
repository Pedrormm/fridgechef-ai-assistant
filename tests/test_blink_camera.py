import time

import pytest

from src.fridgechef.blink_camera import ensure_new_capture_file


def test_new_capture_rejects_exact_same_cached_file(tmp_path):
    photo = tmp_path / "latest.jpg"
    photo.write_bytes(b"old image")
    previous_digest = ""  # first call accepts any fresh file
    ensure_new_capture_file(photo, time.time() - 1, 120, previous_digest)

    previous_digest = __import__("hashlib").sha256(photo.read_bytes()).hexdigest()
    photo.write_bytes(b"old image")

    with pytest.raises(RuntimeError):
        ensure_new_capture_file(photo, time.time() - 1, 120, previous_digest)


def test_new_capture_accepts_changed_file(tmp_path):
    photo = tmp_path / "latest.jpg"
    photo.write_bytes(b"old image")
    previous_digest = __import__("hashlib").sha256(photo.read_bytes()).hexdigest()
    photo.write_bytes(b"new image")

    ensure_new_capture_file(photo, time.time() - 1, 120, previous_digest)
