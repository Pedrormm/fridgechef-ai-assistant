from src.fridgechef import upload_input
from src.fridgechef.upload_input import (
    normalize_image_mime_type,
    read_uploaded_image,
    uploaded_file_identifier,
)


class FakeUpload:
    def __init__(
        self,
        payload: bytes,
        *,
        name: str = "food.jpg",
        mime_type: str = "image/jpeg",
        file_id: str = "upload-1",
    ) -> None:
        self._payload = payload
        self.name = name
        self.type = mime_type
        self.file_id = file_id

    def getvalue(self) -> bytes:
        return self._payload


def test_browser_mime_alias_is_normalized():
    assert normalize_image_mime_type("food.jpg", "image/jpg") == "image/jpeg"


def test_extension_recovers_an_empty_or_generic_browser_mime_type():
    assert normalize_image_mime_type("food.webp", "") == "image/webp"
    assert normalize_image_mime_type("food.png", "application/octet-stream") == "image/png"


def test_supported_extensions_do_not_depend_on_the_operating_system(monkeypatch):
    monkeypatch.setattr(upload_input.mimetypes, "guess_type", lambda *_args, **_kwargs: (None, None))

    assert normalize_image_mime_type("FOOD.WEBP", "") == "image/webp"
    assert normalize_image_mime_type("fridge.JPEG", "application/octet-stream") == "image/jpeg"
    assert normalize_image_mime_type("shelf.PNG", "binary/octet-stream") == "image/png"


def test_unknown_generic_upload_stays_generic(monkeypatch):
    monkeypatch.setattr(upload_input.mimetypes, "guess_type", lambda *_args, **_kwargs: (None, None))

    assert normalize_image_mime_type("food.unknown", "") == "application/octet-stream"
    assert normalize_image_mime_type("food.unknown", "application/octet-stream") == "application/octet-stream"


def test_streamlit_file_id_is_preferred_for_upload_identity():
    upload = FakeUpload(b"image-bytes", file_id="browser-file-id")

    assert uploaded_file_identifier(upload, b"image-bytes") == "streamlit:browser-file-id"


def test_hash_identity_is_available_without_a_streamlit_file_id():
    upload = FakeUpload(b"same-image", file_id="")

    first = uploaded_file_identifier(upload, b"same-image")
    second = uploaded_file_identifier(upload, b"same-image")

    assert first == second
    assert first.startswith("sha256:")


def test_uploaded_file_is_read_once_into_a_normalized_value():
    upload = FakeUpload(
        b"valid-image-content",
        name="fridge.JPEG",
        mime_type="application/octet-stream",
        file_id="file-123",
    )

    result = read_uploaded_image(upload)

    assert result is not None
    assert result.image_bytes == b"valid-image-content"
    assert result.mime_type == "image/jpeg"
    assert result.filename == "fridge.JPEG"
    assert result.upload_id == "streamlit:file-123"
