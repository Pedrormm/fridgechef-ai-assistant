from __future__ import annotations

from pathlib import Path

from scripts.patch_utils import replace_once, replace_regex_once


APP_PATH = Path("streamlit_app/app.py")


def apply_patch() -> None:
    """Add independent prepared-image state and consumed-input cleanup."""
    text = APP_PATH.read_text(encoding="utf-8")
    if "def get_prepared_images()" in text:
        print("Multi-input session state is already applied.")
        return

    text = replace_once(
        text,
        "from src.fridgechef.fridge_qa import answer_fridge_question\n",
        "from src.fridgechef.fridge_qa import answer_fridge_question\n"
        "from src.fridgechef.input_pipeline import (\n"
        "    PreparedImageInput,\n"
        "    build_incoming_inventory,\n"
        "    merge_fridge_analyses,\n"
        ")\n",
        "input pipeline import",
    )
    text = replace_once(
        text,
        "from src.fridgechef.preferences import PreferenceValidationError, validate_profile_preferences\n",
        "from src.fridgechef.preferences import PreferenceValidationError, validate_profile_preferences\n"
        "from src.fridgechef.quantities import (\n"
        "    display_quantity_label,\n"
        "    format_quantity_parts,\n"
        "    parse_quantity_label,\n"
        ")\n",
        "quantity import",
    )
    text = replace_once(
        text,
        '        "current_image_source": "upload",\n        "fridge_inventory": [],\n',
        '        "current_image_source": "upload",\n'
        '        "prepared_images": {},\n'
        '        "manual_input_version": 0,\n'
        '        "upload_widget_version": 0,\n'
        '        "clear_consumed_inputs": False,\n'
        '        "fridge_inventory": [],\n',
        "multi-input session defaults",
    )

    replacement = '''def store_prepared_image(
    image_data: bytes,
    image_mime_type: str,
    caption: str,
    source: InputSource,
) -> None:
    """Keep one image per input channel so every prepared source can be analyzed."""
    prepared = dict(st.session_state.get("prepared_images", {}))
    prepared[source] = {
        "image_bytes": image_data,
        "mime_type": image_mime_type,
        "caption": caption,
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
    )


def get_prepared_images() -> list[PreparedImageInput]:
    """Return every prepared image in a stable processing order."""
    images: list[PreparedImageInput] = []
    for source in ("upload", "device_camera", "internal_camera"):
        image = get_prepared_image(source)
        if image is not None:
            images.append(image)
    return images


def clear_prepared_image(source: InputSource) -> None:
    """Remove one image while preserving the remaining prepared inputs."""
    prepared = dict(st.session_state.get("prepared_images", {}))
    prepared.pop(source, None)
    st.session_state["prepared_images"] = prepared
    if source == "upload":
        st.session_state["upload_widget_version"] = int(
            st.session_state.get("upload_widget_version", 0)
        ) + 1


def reset_consumed_inputs_if_needed() -> None:
    """Clear persisted inputs on the next rerun to prevent accidental double counting."""
    if not st.session_state.get("clear_consumed_inputs"):
        return
    st.session_state["prepared_images"] = {}
    st.session_state["manual_input_version"] = int(
        st.session_state.get("manual_input_version", 0)
    ) + 1
    st.session_state["upload_widget_version"] = int(
        st.session_state.get("upload_widget_version", 0)
    ) + 1
    st.session_state["clear_consumed_inputs"] = False


def capture_internal_camera_with_feedback() -> None:'''
    text = replace_regex_once(
        text,
        r"def store_current_image\(.*?\n\n\ndef capture_internal_camera_with_feedback\(\) -> None:",
        replacement,
        "prepared image helpers",
    )
    text = replace_once(
        text,
        '            store_current_image(image_bytes, "image/jpeg", "Foto de cámara interna", "internal_camera")\n',
        '            store_prepared_image(image_bytes, "image/jpeg", "Foto de cámara interna", "internal_camera")\n',
        "internal camera storage",
    )
    text = replace_once(
        text,
        '            st.success("Foto realizada correctamente.")\n            st.image(image_bytes, caption="Foto preparada", use_container_width=True)\n',
        '            st.success("Foto realizada correctamente.")\n',
        "internal camera duplicate preview",
    )
    text = replace_once(
        text,
        "init_state()\ninstall_streamlit_i18n(st, current_language)\n",
        "init_state()\nreset_consumed_inputs_if_needed()\ninstall_streamlit_i18n(st, current_language)\n",
        "consumed input reset call",
    )

    APP_PATH.write_text(text, encoding="utf-8")
    print("Applied independent prepared-image state.")


if __name__ == "__main__":
    apply_patch()
