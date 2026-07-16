from pathlib import Path


APP_PATH = Path("streamlit_app/app.py")


def _app_source() -> str:
    return APP_PATH.read_text(encoding="utf-8")


def test_app_keeps_all_input_channels_independent():
    source = _app_source()

    assert "def get_prepared_images()" in source
    assert 'get_prepared_image("upload")' in source
    assert 'get_prepared_image("device_camera")' in source
    assert 'get_prepared_image("internal_camera")' in source
    assert "prepared_images = get_prepared_images()" in source
    assert "use_prepared_image" not in source


def test_native_file_upload_is_prepared_in_an_on_change_callback():
    source = _app_source()

    assert "def prepare_uploaded_image_from_widget" in source
    assert "on_change=prepare_uploaded_image_from_widget" in source
    assert "uploaded is not None" in source
    assert "read_uploaded_image" in source
    assert 'st.image(upload_image.image_bytes, caption="Foto preparada"' in source


def test_new_upload_event_survives_consumed_input_cleanup():
    source = _app_source()

    assert "def mark_prepared_images_consumed" in source
    assert 'st.session_state["consumed_input_ids"]' in source
    assert "input_id != str(consumed.get(source) or \"\")" in source
    assert "mark_prepared_images_consumed(images)" in source


def test_file_uploader_css_does_not_hide_native_file_state():
    source = _app_source()

    assert '[data-testid="stFileUploaderDropzone"] button *' not in source
    assert '[data-testid="stFileUploaderFileName"] *' not in source
    assert "color: transparent !important" not in source.split(
        '[data-testid="stFileUploader"]', 1
    )[1].split('[data-testid="stCameraInput"] p,', 1)[0]


def test_app_uses_atomic_multi_input_inventory_pipeline():
    source = _app_source()

    assert "build_incoming_inventory" in source
    assert "merge_fridge_analyses" in source
    assert 'st.session_state["clear_consumed_inputs"] = True' in source
    assert "if not incoming_items:" in source
    assert "set_inventory(update_result.inventory, persist=True)" in source


def test_empty_detection_messages_match_the_persistence_mode():
    source = _app_source()

    assert 'if remember_fridge and get_inventory()' in source
    assert 'else "No se ha guardado ningún cambio."' in source
    assert "the fridge had {previous_quantity}" in source


def test_previous_mobile_and_widget_key_fixes_are_preserved():
    source = _app_source()

    assert 'preferred_facing_mode="environment"' in source
    assert 'widget_namespace="saved_inventory_top"' in source
    assert 'widget_namespace="saved_inventory_analysis_result"' in source
    assert "inventory_action_key" in source


def test_generate_flow_refreshes_inventory_then_renders_only_recipes():
    source = _app_source()
    generate_section = source.split("if recipes_clicked:", 1)[1]
    generate_action, replay_section = generate_section.split(
        "# Replay successful actions after the refresh", 1
    )

    assert "analyze_current_inputs(" in generate_action
    assert 'st.session_state["show_last_recipes_once"] = True' in generate_action
    assert "st.rerun()" in generate_action
    assert 'title="Alimentos detectados"' not in generate_action
    assert "show_manual_feedback" not in generate_action
    assert "show_inventory_update" not in generate_action

    assert "show_recipes(" in replay_section
    assert "RecipeResponse.model_validate(recipe_payload)" in replay_section
