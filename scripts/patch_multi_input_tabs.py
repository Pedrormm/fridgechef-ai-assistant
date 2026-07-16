from __future__ import annotations

from pathlib import Path

from scripts.patch_utils import replace_once, replace_regex_once


APP_PATH = Path("streamlit_app/app.py")


def apply_patch() -> None:
    """Render manual text and three independent image channels simultaneously."""
    text = APP_PATH.read_text(encoding="utf-8")
    if "prepared_images = get_prepared_images()" in text:
        print("Four-channel input tabs are already applied.")
        return

    replacement = '''available_tabs = ["Formulario", "Subir foto"]
if can_offer_device_camera():
    available_tabs.append("Cámara del dispositivo")
available_tabs.append("Cámara interna")

tabs = st.tabs(available_tabs)
manual_text = ""

with tabs[0]:
    manual_text = st.text_area(
        "Ingredientes manuales",
        placeholder="Ejemplo: huevos, arroz, tomate, calabacín, queso",
        help=(
            "Puedes mezclar frases normales con ingredientes. La app separará los alimentos "
            "y descartará lo que no sirva para la nevera."
        ),
        key=f"manual_ingredients_{st.session_state.get('manual_input_version', 0)}",
    )
    if manual_text.strip():
        st.caption(
            "Revisaré el texto al pulsar Analizar nevera o Generar recetas para evitar "
            "llamadas innecesarias mientras escribes."
        )

with tabs[1]:
    uploaded = st.file_uploader(
        "Sube una foto de alimentos (JPG, PNG o WEBP)",
        type=["jpg", "jpeg", "png", "webp"],
        key=f"fridge_upload_{st.session_state.get('upload_widget_version', 0)}",
        max_upload_size=settings.max_image_mb,
    )
    if uploaded:
        image_bytes = uploaded.getvalue()
        mime_type = uploaded.type or mimetypes.guess_type(uploaded.name)[0] or "image/jpeg"
        validate_image_upload(image_bytes, mime_type, settings.max_image_mb)
        store_prepared_image(image_bytes, mime_type, "Foto subida", "upload")

    upload_image = get_prepared_image("upload")
    if upload_image:
        st.image(upload_image.image_bytes, caption="Foto preparada", use_container_width=True)
        if st.button("Quitar foto subida", key="clear_upload_photo", use_container_width=True):
            clear_prepared_image("upload")
            st.rerun()

current_tab_index = 2
if "Cámara del dispositivo" in available_tabs:
    with tabs[current_tab_index]:
        st.write("Haz una foto de la nevera o de los alimentos directamente desde este dispositivo.")
        st.caption(
            "La cámara trasera se abre de forma predeterminada. "
            "Puedes cambiar de cámara cuando el dispositivo disponga de más de una."
        )
        try:
            device_capture = rear_camera_input(
                key="device_camera_rear",
                max_image_mb=settings.max_image_mb,
                preferred_facing_mode="environment",
                capture_label=t("Hacer foto"),
                switch_label=t("Cambiar cámara"),
                starting_label=t("Abriendo la cámara trasera…"),
            )
        except Exception:
            device_capture = None
            st.warning(
                "No he podido preparar la cámara de este dispositivo. "
                "Puedes continuar desde la pestaña Subir foto."
            )

        if device_capture:
            previous_capture_id = st.session_state.get("last_device_camera_capture_id")
            if device_capture.capture_id != previous_capture_id:
                try:
                    validate_image_upload(
                        device_capture.image_bytes,
                        device_capture.mime_type,
                        settings.max_image_mb,
                    )
                    store_prepared_image(
                        device_capture.image_bytes,
                        device_capture.mime_type,
                        "Foto del dispositivo",
                        "device_camera",
                    )
                    st.session_state["last_device_camera_capture_id"] = device_capture.capture_id
                    st.success("Foto realizada correctamente.")
                except ImageValidationError as exc:
                    st.error(str(exc))
                except Exception:
                    st.error(
                        "No he podido preparar la foto realizada. "
                        "Vuelve a intentarlo o usa la pestaña Subir foto."
                    )

        device_image = get_prepared_image("device_camera")
        if device_image:
            st.image(device_image.image_bytes, caption="Foto preparada", use_container_width=True)
            if st.button(
                "Quitar foto del dispositivo",
                key="clear_device_photo",
                use_container_width=True,
            ):
                clear_prepared_image("device_camera")
                st.rerun()
    current_tab_index += 1

with tabs[current_tab_index]:
    st.write("Asegúrate de tener conectada una cámara dentro de la nevera para poder usar esta opción.")
    if st.button("Hacer foto con cámara interna"):
        capture_internal_camera_with_feedback()

    internal_image = get_prepared_image("internal_camera")
    if internal_image:
        st.image(internal_image.image_bytes, caption="Foto preparada", use_container_width=True)
        if st.button(
            "Quitar foto de la cámara interna",
            key="clear_internal_photo",
            use_container_width=True,
        ):
            clear_prepared_image("internal_camera")
            st.rerun()

prepared_images = get_prepared_images()
if prepared_images:
    prepared_labels = ", ".join(image.caption for image in prepared_images)
    st.caption(f"Entradas de imagen preparadas: {prepared_labels}")

confirm_replace = False'''
    text = replace_regex_once(
        text,
        r"available_tabs = \[\"Formulario\", \"Subir foto\"\].*?\n\nconfirm_replace = False",
        replacement,
        "four-channel input UI",
    )
    text = replace_once(
        text,
        "has_available_input = bool(manual_text.strip() or use_prepared_image or (remember_fridge and get_inventory()))\n",
        "has_available_input = bool(manual_text.strip() or prepared_images or (remember_fridge and get_inventory()))\n",
        "available input check",
    )
    text = text.replace(
        "                use_prepared_image,\n",
        "                prepared_images,\n",
    )
    text = text.replace(
        '                "Revisando la foto si hay una imagen preparada.",\n',
        '                "Revisando todas las fotos que has preparado.",\n',
    )
    if "use_prepared_image" in text:
        raise RuntimeError("The legacy single-image flag is still present after patching.")

    APP_PATH.write_text(text, encoding="utf-8")
    print("Applied simultaneous manual, upload, device and internal inputs.")


if __name__ == "__main__":
    apply_patch()
