from pathlib import Path


COMPONENT_DIR = Path("src/fridgechef/components/mobile_upload")
APP_PATH = Path("streamlit_app/app.py")


def test_mobile_upload_frontend_uses_gallery_file_input_and_browser_resizing():
    html = (COMPONENT_DIR / "index.html").read_text(encoding="utf-8")
    javascript = (COMPONENT_DIR / "main.js").read_text(encoding="utf-8")

    assert 'type="file"' in html
    assert "capture=" not in html
    assert ".jpg,.jpeg,.png,.webp" in html
    assert "createImageBitmap" in javascript
    assert "canvas.toBlob" in javascript
    assert "maxOutputBytes" in javascript
    assert "Streamlit.setComponentValue" in javascript
    assert "input.value = \"\"" in javascript


def test_mobile_upload_frontend_reports_progress_and_friendly_failures():
    javascript = (COMPONENT_DIR / "main.js").read_text(encoding="utf-8")

    assert "processingLabel" in javascript
    assert "readyLabel" in javascript
    assert "unsupportedLabel" in javascript
    assert "tooLargeLabel" in javascript
    assert "failedLabel" in javascript
    assert "emitFailure" in javascript


def test_streamlit_app_uses_mobile_component_without_replacing_desktop_uploader():
    source = APP_PATH.read_text(encoding="utf-8")
    upload_block = source.split("with tabs[1]:", 1)[1].split("current_tab_index = 2", 1)[0]

    assert "mobile_image_upload" in source
    assert "if can_offer_device_camera():" in upload_block
    assert "mobile_image_upload(" in upload_block
    assert "else:" in upload_block
    assert "st.file_uploader(" in upload_block
    assert "store_prepared_image(" in upload_block
    assert 'input_id=mobile_uploaded.upload_id' in upload_block
