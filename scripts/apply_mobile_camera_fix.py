from __future__ import annotations

from pathlib import Path


APP_PATH = Path("streamlit_app/app.py")


def replace_once(text: str, old: str, new: str, description: str) -> str:
    """Replace one exact source block and fail loudly when the source changed."""
    occurrences = text.count(old)
    if occurrences != 1:
        raise RuntimeError(
            f"Expected exactly one {description} block, found {occurrences}. "
            "Review streamlit_app/app.py before applying this patch."
        )
    return text.replace(old, new, 1)


def apply_patch() -> None:
    """Apply the rear-camera and inventory widget-key changes idempotently."""
    text = APP_PATH.read_text(encoding="utf-8")
    if "from src.fridgechef.device_camera import rear_camera_input" in text:
        print("Mobile camera fix is already applied.")
        return

    text = replace_once(
        text,
        "from src.fridgechef.config import get_settings\n",
        "from src.fridgechef.config import get_settings\n"
        "from src.fridgechef.device_camera import rear_camera_input\n",
        "device camera import",
    )
    text = replace_once(
        text,
        "from src.fridgechef.theme import build_theme_css, theme_label, theme_options\n",
        "from src.fridgechef.theme import build_theme_css, theme_label, theme_options\n"
        "from src.fridgechef.ui_keys import inventory_action_key\n",
        "UI key import",
    )
    text = replace_once(
        text,
        'def show_inventory(inventory: list[InventoryItem], title: str = "Alimentos guardados", editable: bool = False) -> None:\n'
        '    """Display the fridge inventory as friendly cards, optionally with edit/delete actions."""\n',
        'def show_inventory(\n'
        '    inventory: list[InventoryItem],\n'
        '    title: str = "Alimentos guardados",\n'
        '    editable: bool = False,\n'
        '    widget_namespace: str | None = None,\n'
        ') -> None:\n'
        '    """Display inventory cards with widget keys scoped to this rendered section."""\n',
        "inventory renderer signature",
    )
    text = replace_once(
        text,
        "    columns = st.columns(2)\n    for index, item in enumerate(inventory):\n",
        "    key_scope = _selector_key(widget_namespace or f\"{title}_{'editable' if editable else 'readonly'}\")\n"
        "    columns = st.columns(2)\n"
        "    for index, item in enumerate(inventory):\n",
        "inventory key scope",
    )
    text = replace_once(
        text,
        'key=f"edit_inventory_{base_key}"',
        'key=inventory_action_key(key_scope, "edit", base_key, index)',
        "inventory edit key",
    )
    text = replace_once(
        text,
        'key=f"delete_inventory_{base_key}"',
        'key=inventory_action_key(key_scope, "delete", base_key, index)',
        "inventory delete key",
    )
    text = replace_once(
        text,
        '    show_inventory(get_inventory(), title="Alimentos guardados", editable=True)\n',
        '    show_inventory(\n'
        '        get_inventory(),\n'
        '        title="Alimentos guardados",\n'
        '        editable=True,\n'
        '        widget_namespace="saved_inventory_top",\n'
        '    )\n',
        "top inventory call",
    )
    text = replace_once(
        text,
        '        st.write("Haz una foto de la nevera o de los alimentos directamente desde este dispositivo.")\n'
        '        st.caption("El navegador te pedirá permiso para usar la cámara cuando sea necesario.")\n'
        '        device_photo = st.camera_input("Hacer foto desde este dispositivo", key="device_camera_photo")\n'
        '        if device_photo:\n'
        '            image_bytes = device_photo.getvalue()\n'
        '            mime_type = device_photo.type or "image/jpeg"\n'
        '            store_current_image(image_bytes, mime_type, "Foto del dispositivo", "device_camera")\n'
        '            st.success("Foto realizada correctamente.")\n'
        '            st.image(image_bytes, caption="Foto preparada", use_container_width=True)\n',
        '        st.write("Haz una foto de la nevera o de los alimentos directamente desde este dispositivo.")\n'
        '        st.caption(\n'
        '            "La cámara trasera se abre de forma predeterminada. "\n'
        '            "Puedes cambiar de cámara cuando el dispositivo disponga de más de una."\n'
        '        )\n'
        '        try:\n'
        '            device_capture = rear_camera_input(\n'
        '                key="device_camera_rear",\n'
        '                max_image_mb=settings.max_image_mb,\n'
        '                preferred_facing_mode="environment",\n'
        '                capture_label=t("Hacer foto"),\n'
        '                switch_label=t("Cambiar cámara"),\n'
        '                starting_label=t("Abriendo la cámara trasera…"),\n'
        '            )\n'
        '        except Exception:\n'
        '            device_capture = None\n'
        '            st.warning(\n'
        '                "No he podido preparar la cámara de este dispositivo. "\n'
        '                "Puedes continuar desde la pestaña Subir foto."\n'
        '            )\n'
        '\n'
        '        if device_capture:\n'
        '            previous_capture_id = st.session_state.get("last_device_camera_capture_id")\n'
        '            if device_capture.capture_id != previous_capture_id:\n'
        '                try:\n'
        '                    validate_image_upload(\n'
        '                        device_capture.image_bytes,\n'
        '                        device_capture.mime_type,\n'
        '                        settings.max_image_mb,\n'
        '                    )\n'
        '                    store_current_image(\n'
        '                        device_capture.image_bytes,\n'
        '                        device_capture.mime_type,\n'
        '                        "Foto del dispositivo",\n'
        '                        "device_camera",\n'
        '                    )\n'
        '                    st.session_state["last_device_camera_capture_id"] = device_capture.capture_id\n'
        '                    st.success("Foto realizada correctamente.")\n'
        '                except ImageValidationError as exc:\n'
        '                    st.error(str(exc))\n'
        '                except Exception:\n'
        '                    st.error(\n'
        '                        "No he podido preparar la foto realizada. "\n'
        '                        "Vuelve a intentarlo o usa la pestaña Subir foto."\n'
        '                    )\n'
        '\n'
        '        current_device_image, _, current_device_source = get_current_image()\n'
        '        if current_device_image and current_device_source == "device_camera":\n'
        '            st.image(current_device_image, caption="Foto preparada", use_container_width=True)\n',
        "device camera block",
    )
    text = replace_once(
        text,
        '                show_inventory(get_inventory(), title="Alimentos guardados actualmente", editable=True)\n',
        '                show_inventory(\n'
        '                    get_inventory(),\n'
        '                    title="Alimentos guardados actualmente",\n'
        '                    editable=True,\n'
        '                    widget_namespace="saved_inventory_analysis_result",\n'
        '                )\n',
        "analysis-result inventory call",
    )

    APP_PATH.write_text(text, encoding="utf-8")
    print("Applied mobile rear-camera and inventory widget-key fixes.")


if __name__ == "__main__":
    apply_patch()
