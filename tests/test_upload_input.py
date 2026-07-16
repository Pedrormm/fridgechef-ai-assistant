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
