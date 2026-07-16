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


def test_generate_flow_renders_recipes_without_detected_food_feedback():
    source = _app_source()
    generate_block = source.split("if recipes_clicked:", 1)[1]

    assert "show_recipes(response, profile" in generate_block
    assert 'title="Alimentos detectados"' not in generate_block
    final_result_block = generate_block.split("if result:", 1)[1]
    assert "show_manual_feedback" not in final_result_block
    assert "show_inventory_update" not in final_result_block
