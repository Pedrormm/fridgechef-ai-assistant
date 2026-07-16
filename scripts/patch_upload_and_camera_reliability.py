from __future__ import annotations

from pathlib import Path

from scripts.patch_utils import replace_once, replace_regex_once


APP_PATH = Path("streamlit_app/app.py")


def apply_patch() -> None:
    """Make uploaded images event-safe and preserve new files during input cleanup."""
    text = APP_PATH.read_text(encoding="utf-8")
    if "def prepare_uploaded_image_from_widget" in text:
        print("Upload and live-camera reliability patch is already applied.")
        return

    text = replace_once(
        text,
        "from src.fridgechef.theme import build_theme_css, theme_label, theme_options\n",
        "from src.fridgechef.theme import build_theme_css, theme_label, theme_options\n"
        "from src.fridgechef.upload_input import read_uploaded_image\n",
        "uploaded image import",
    )
    text = replace_once(
        text,
        '        "clear_consumed_inputs": False,\n        "fridge_inventory": [],\n',
        '        "clear_consumed_inputs": False,\n'
        '        "consumed_input_ids": {},\n'
        '        "upload_notice": "",\n'
        '        "upload_error": "",\n'
        '        "fridge_inventory": [],\n',
        "upload session defaults",
    )

    helper_block = '''def current_upload_widget_key() -> str:
    """Return the current native uploader key used by Streamlit."""
    version = int(st.session_state.get("upload_widget_version", 0))
    return f"fridge_upload_{version}"


def store_prepared_image(
    image_data: bytes,
    image_mime_type: str,
    caption: str,
    source: InputSource,
    *,
    input_id: str = "",
    filename: str = "",
) -> None:
    """Keep one image per input channel so every prepared source can be analyzed."""
    prepared = dict(st.session_state.get("prepared_images", {}))
    prepared[source] = {
        "image_bytes": image_data,
        "mime_type": image_mime_type,
        "caption": caption,
        "input_id": input_id,
        "filename": filename,
    }
    st.session_state["prepared_images"] = prepared


def get_prepared_image(source: InputSource) -> PreparedImageInput | None:
    """Return one prepared image without affecting the other input channels."""
    payload = st.session_state.get("prepared_images", {}).get(source)
    if not isinstance(payload, dict) or not payload.get("image_bytes"):
        return None
    return PreparedImageInput(
        source=source,
        image_bytes=payload["image_bytes"],
        mime_type=str(payload.get("mime_type") or "image/jpeg"),
        caption=str(payload.get("caption") or "Foto preparada"),
        input_id=str(payload.get("input_id") or ""),
        filename=str(payload.get("filename") or ""),
    )


def get_prepared_images() -> list[PreparedImageInput]:
    """Return every prepared image in a stable processing order."""
    images: list[PreparedImageInput] = []
    for source in ("upload", "device_camera", "internal_camera"):
        image = get_prepared_image(source)
        if image is not None:
            images.append(image)
    return images


def clear_prepared_image(source: InputSource, *, reset_widget: bool = True) -> None:
    """Remove one image while preserving the remaining prepared inputs."""
    prepared = dict(st.session_state.get("prepared_images", {}))
    prepared.pop(source, None)
    st.session_state["prepared_images"] = prepared
    if source == "upload":
        st.session_state["upload_notice"] = ""
        st.session_state["upload_error"] = ""
        if reset_widget:
            st.session_state["upload_widget_version"] = int(
                st.session_state.get("upload_widget_version", 0)
            ) + 1


def prepare_uploaded_image(uploaded_file) -> bool:
    """Validate and persist one native file-uploader value immediately."""
    try:
        uploaded_image = read_uploaded_image(uploaded_file)
        if uploaded_image is None:
            return False
        validate_image_upload(
            uploaded_image.image_bytes,
            uploaded_image.mime_type,
            settings.max_image_mb,
        )
    except ImageValidationError as exc:
        clear_prepared_image("upload", reset_widget=False)
        st.session_state["upload_error"] = str(exc)
        return False
    except Exception:
        clear_prepared_image("upload", reset_widget=False)
        st.session_state["upload_error"] = (
            "No he podido preparar esta foto. Prueba con otra imagen JPG, PNG o WEBP."
        )
        return False

    current = get_prepared_image("upload")
    if current is None or current.input_id != uploaded_image.upload_id:
        store_prepared_image(
            uploaded_image.image_bytes,
            uploaded_image.mime_type,
            "Foto subida",
            "upload",
            input_id=uploaded_image.upload_id,
            filename=uploaded_image.filename,
        )
    st.session_state["upload_error"] = ""
    st.session_state["upload_notice"] = (
        f"Foto preparada correctamente: {uploaded_image.filename}."
    )
    return True


def prepare_uploaded_image_from_widget(widget_key: str) -> None:
    """Copy the selected file during Streamlit's on-change callback."""
    uploaded_file = st.session_state.get(widget_key)
    if uploaded_file is None:
        clear_prepared_image("upload", reset_widget=False)
        return
    prepare_uploaded_image(uploaded_file)


def mark_prepared_images_consumed(images: list[PreparedImageInput]) -> None:
    """Remember which prepared inputs were used by the completed action."""
    st.session_state["consumed_input_ids"] = {
        image.source: image.input_id
        for image in images
        if image.input_id
    }


def reset_consumed_inputs_if_needed() -> None:
    """Clear consumed inputs without discarding a newly selected upload event."""
    if not st.session_state.get("clear_consumed_inputs"):
        return

    prepared = dict(st.session_state.get("prepared_images", {}))
    consumed = dict(st.session_state.get("consumed_input_ids", {}))
    preserved: dict[str, dict] = {}
    for source, payload in prepared.items():
        if not isinstance(payload, dict):
            continue
        input_id = str(payload.get("input_id") or "")
        if input_id and input_id != str(consumed.get(source) or ""):
            preserved[source] = payload

    st.session_state["prepared_images"] = preserved
    st.session_state["manual_input_version"] = int(
        st.session_state.get("manual_input_version", 0)
    ) + 1
    st.session_state["upload_widget_version"] = int(
        st.session_state.get("upload_widget_version", 0)
    ) + 1
    st.session_state["consumed_input_ids"] = {}
    st.session_state["clear_consumed_inputs"] = False


def capture_internal_camera_with_feedback() -> None:'''
    text = replace_regex_once(
        text,
        r"def store_prepared_image\(.*?\n\n\ndef capture_internal_camera_with_feedback\(\) -> None:",
        helper_block,
        "prepared image helper block",
    )

    text = replace_once(
        text,
        '            store_prepared_image(image_bytes, "image/jpeg", "Foto de cámara interna", "internal_camera")\n',
        '            internal_input_id = f"blink:{Path(output).stat().st_mtime_ns}:{len(image_bytes)}"\n'
        '            store_prepared_image(\n'
        '                image_bytes,\n'
        '                "image/jpeg",\n'
        '                "Foto de cámara interna",\n'
        '                "internal_camera",\n'
        '                input_id=internal_input_id,\n'
        '                filename=Path(output).name,\n'
        '            )\n',
        "internal camera prepared image",
    )
    text = replace_once(
        text,
        '                    store_prepared_image(\n'
        '                        device_capture.image_bytes,\n'
        '                        device_capture.mime_type,\n'
        '                        "Foto del dispositivo",\n'
        '                        "device_camera",\n'
        '                    )\n',
        '                    store_prepared_image(\n'
        '                        device_capture.image_bytes,\n'
        '                        device_capture.mime_type,\n'
        '                        "Foto del dispositivo",\n'
        '                        "device_camera",\n'
        '                        input_id=device_capture.capture_id,\n'
        '                        filename="device-camera.jpg",\n'
        '                    )\n',
        "device camera prepared image",
    )

    upload_block = '''with tabs[1]:
    upload_key = current_upload_widget_key()
    uploaded = st.file_uploader(
        "Sube una foto de alimentos (JPG, PNG o WEBP)",
        type=["jpg", "jpeg", "png", "webp"],
        key=upload_key,
        max_upload_size=settings.max_image_mb,
        on_change=prepare_uploaded_image_from_widget,
        args=(upload_key,),
    )
    if uploaded is not None:
        # The callback is the primary path. This fallback also covers browser or
        # Streamlit versions that restore the widget value without firing it.
        prepare_uploaded_image(uploaded)

    if st.session_state.get("upload_error"):
        st.error(st.session_state["upload_error"], __skip_i18n=True)

    upload_image = get_prepared_image("upload")
    if upload_image:
        notice = st.session_state.get("upload_notice") or "Foto preparada correctamente."
        st.success(notice, __skip_i18n=True)
        st.image(upload_image.image_bytes, caption="Foto preparada", use_container_width=True)
        if st.button("Quitar foto subida", key="clear_upload_photo", use_container_width=True):
            clear_prepared_image("upload")
            st.rerun()

current_tab_index = 2'''
    text = replace_regex_once(
        text,
        r"with tabs\[1\]:.*?\n\ncurrent_tab_index = 2",
        upload_block,
        "native uploaded image tab",
    )

    safe_uploader_css = '''            [data-testid="stFileUploader"],
            [data-testid="stCameraInput"] {
                border: 1px solid rgba(45, 49, 66, 0.08);
                border-radius: 16px;
                background: rgba(246, 247, 251, 0.88);
            }
            [data-testid="stFileUploaderDropzone"] {
                border-radius: 14px !important;
            }
            [data-testid="stFileUploaderDropzone"] button,
            [data-testid="stCameraInput"] button {
                border-radius: 12px !important;
                min-width: 8.7rem !important;
                font-weight: 600 !important;
            }
'''
    text = replace_regex_once(
        text,
        r'            \[data-testid="stFileUploader"\],.*?(?=            \[data-testid="stCameraInput"\] p,)',
        safe_uploader_css,
        "file uploader CSS",
    )

    text = replace_once(
        text,
        '        set_inventory(update_result.inventory, persist=True)\n'
        '        st.session_state["clear_consumed_inputs"] = True\n',
        '        set_inventory(update_result.inventory, persist=True)\n'
        '        mark_prepared_images_consumed(images)\n'
        '        st.session_state["clear_consumed_inputs"] = True\n',
        "consumed prepared image tracking",
    )

    APP_PATH.write_text(text, encoding="utf-8")
    print("Applied reliable uploaded images and event-safe input cleanup.")


if __name__ == "__main__":
    apply_patch()
