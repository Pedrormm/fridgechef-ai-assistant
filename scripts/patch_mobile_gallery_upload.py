from __future__ import annotations

from pathlib import Path

from scripts.patch_utils import replace_once, replace_regex_once


APP_PATH = Path("streamlit_app/app.py")


def apply_patch() -> None:
    """Use a browser-side image picker on mobile while preserving desktop uploads."""
    text = APP_PATH.read_text(encoding="utf-8")
    if "from src.fridgechef.mobile_upload import mobile_image_upload" in text:
        print("Mobile gallery upload patch is already applied.")
        return

    text = replace_once(
        text,
        "from src.fridgechef.device_camera import rear_camera_input\n",
        "from src.fridgechef.device_camera import rear_camera_input\n"
        "from src.fridgechef.mobile_upload import mobile_image_upload\n",
        "mobile upload import",
    )

    mobile_upload_block = '''with tabs[1]:
    if can_offer_device_camera():
        mobile_upload_key = (
            f"mobile_fridge_upload_{st.session_state.get('upload_widget_version', 0)}"
        )
        try:
            mobile_uploaded = mobile_image_upload(
                key=mobile_upload_key,
                max_source_mb=max(settings.max_image_mb, 25),
                max_output_mb=max(1, min(settings.max_image_mb, 3)),
                max_dimension=1920,
                select_label=t("Seleccionar foto"),
                processing_label=t("Preparando la foto…"),
                ready_label=t("Foto preparada. Ya puedes analizarla."),
                unsupported_label=t("Este formato no es compatible. Usa JPG, PNG o WEBP."),
                too_large_label=t("La foto es demasiado grande para prepararla."),
                failed_label=t("No he podido preparar esta foto. Prueba con otra imagen."),
            )
        except Exception:
            mobile_uploaded = None
            st.session_state["upload_error"] = (
                "No he podido abrir el selector de fotos. Recarga la página y vuelve a intentarlo."
            )

        if mobile_uploaded is not None:
            if mobile_uploaded.error:
                clear_prepared_image("upload", reset_widget=False)
                st.session_state["upload_error"] = mobile_uploaded.error
            elif mobile_uploaded.ok:
                try:
                    validate_image_upload(
                        mobile_uploaded.image_bytes or b"",
                        mobile_uploaded.mime_type,
                        settings.max_image_mb,
                    )
                    current_upload = get_prepared_image("upload")
                    if current_upload is None or current_upload.input_id != mobile_uploaded.upload_id:
                        store_prepared_image(
                            mobile_uploaded.image_bytes or b"",
                            mobile_uploaded.mime_type,
                            "Foto subida",
                            "upload",
                            input_id=mobile_uploaded.upload_id,
                            filename=mobile_uploaded.filename,
                        )
                    st.session_state["upload_error"] = ""
                    st.session_state["upload_notice"] = (
                        f"Foto preparada correctamente: {mobile_uploaded.filename}."
                    )
                except ImageValidationError as exc:
                    clear_prepared_image("upload", reset_widget=False)
                    st.session_state["upload_error"] = str(exc)
                except Exception:
                    clear_prepared_image("upload", reset_widget=False)
                    st.session_state["upload_error"] = (
                        "No he podido preparar esta foto. Prueba con otra imagen JPG, PNG o WEBP."
                    )
    else:
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
        mobile_upload_block,
        "upload tab",
    )

    APP_PATH.write_text(text, encoding="utf-8")
    print("Applied mobile gallery upload fallback with browser-side resizing.")


if __name__ == "__main__":
    apply_patch()
