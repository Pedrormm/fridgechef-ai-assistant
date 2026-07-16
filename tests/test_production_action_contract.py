from pathlib import Path


APP_SOURCE = Path("streamlit_app/app.py").read_text(encoding="utf-8")
RECIPE_IMAGE_SOURCE = Path("src/fridgechef/recipe_images.py").read_text(encoding="utf-8")


def test_successful_actions_refresh_the_top_inventory_before_rendering_results():
    assert 'st.session_state["show_last_analysis_once"] = True' in APP_SOURCE
    assert 'st.session_state["show_last_recipes_once"] = True' in APP_SOURCE
    assert '# Replay successful actions after the refresh' in APP_SOURCE
    assert 'restored_response = RecipeResponse.model_validate(recipe_payload)' in APP_SOURCE
    assert 'restored_update = InventoryUpdateResult.model_validate(update_payload)' in APP_SOURCE


def test_recipe_generation_keeps_inventory_persistence_without_showing_detection_cards():
    recipe_action_start = APP_SOURCE.index("if recipes_clicked:")
    recipe_action = APP_SOURCE[recipe_action_start:]

    assert "analyze_current_inputs(" in recipe_action
    assert 'st.session_state["last_recipes"] = response.model_dump()' in recipe_action
    assert "show_inventory_update(update_result)" not in recipe_action.split(
        "# Replay successful actions after the refresh", 1
    )[0]


def test_removed_streamlit_width_argument_cannot_emit_deprecation_warnings():
    assert "use_container_width=" not in APP_SOURCE
    assert 'width="stretch"' in APP_SOURCE


def test_recipe_images_have_a_local_fallback_and_no_retired_model_calls():
    assert 'used_model = "local-recipe-card-v1"' in RECIPE_IMAGE_SOURCE
    assert "_generate_image_with_interactions(" not in RECIPE_IMAGE_SOURCE[
        RECIPE_IMAGE_SOURCE.index("def _try_generate_image"):RECIPE_IMAGE_SOURCE.index(
            "def generate_recipe_image"
        )
    ]
    strategy = RECIPE_IMAGE_SOURCE[
        RECIPE_IMAGE_SOURCE.index("def _try_generate_image"):RECIPE_IMAGE_SOURCE.index(
            "def generate_recipe_image"
        )
    ]
    assert "_generate_image_with_imagen_sdk" not in strategy
    assert "_generate_image_with_imagen_rest" not in strategy
