from __future__ import annotations

from pathlib import Path

from scripts.patch_utils import replace_once, replace_regex_once


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "streamlit_app" / "app.py"
RECIPE_IMAGES_PATH = PROJECT_ROOT / "src" / "fridgechef" / "recipe_images.py"


def _patch_app(source: str) -> str:
    """Materialize inventory refresh and one-shot action result replay in Streamlit."""
    if "from src.fridgechef.action_results import (" not in source:
        source = replace_once(
            source,
            "from src.fridgechef.app_preferences import (\n",
            "from src.fridgechef.action_results import (\n"
            "    restore_manual_parse_result,\n"
            "    snapshot_manual_parse_result,\n"
            ")\n"
            "from src.fridgechef.app_preferences import (\n",
            "action-result import",
        )

    if '"show_last_analysis_once": False' not in source:
        source = replace_once(
            source,
            '        "last_analysis": None,\n'
            '        "last_update": None,\n'
            '        "last_recipes": None,\n'
            '        "inventory_clear_message": "",\n',
            '        "last_analysis": None,\n'
            '        "last_update": None,\n'
            '        "last_manual_parse_result": None,\n'
            '        "last_recipes": None,\n'
            '        "last_recipe_images_enabled": False,\n'
            '        "show_last_analysis_once": False,\n'
            '        "show_last_recipes_once": False,\n'
            '        "inventory_clear_message": "",\n',
            "action replay session defaults",
        )

    old_analysis_result = '''        if result:
            _, update_result, parse_result = result
            show_manual_feedback(parse_result)
            if update_result:
                show_inventory_update(update_result)
                show_inventory(update_result.inventory, title="Alimentos detectados")
            elif remember_fridge and get_inventory():
                st.info("No se han introducido alimentos nuevos. Mantengo la nevera guardada tal como estaba.")
                show_inventory(
                    get_inventory(),
                    title="Alimentos guardados actualmente",
                    editable=True,
                    widget_namespace="saved_inventory_analysis_result",
                )
'''
    new_analysis_result = '''        if result:
            _, _, parse_result = result
            # Rerun once so the saved inventory rendered above reflects the atomic update.
            st.session_state["last_manual_parse_result"] = snapshot_manual_parse_result(parse_result)
            st.session_state["show_last_analysis_once"] = True
            st.rerun()
'''
    if 'st.session_state["show_last_analysis_once"] = True' not in source:
        source = replace_once(
            source,
            old_analysis_result,
            new_analysis_result,
            "successful analysis result block",
        )

    old_recipe_state = '''            st.session_state["last_recipes"] = response.model_dump()
            return parse_result, update_result, response
'''
    new_recipe_state = '''            st.session_state["last_recipes"] = response.model_dump()
            st.session_state["last_recipe_images_enabled"] = bool(generate_recipe_images)
            st.session_state["show_last_recipes_once"] = True
            return parse_result, update_result, response
'''
    if 'st.session_state["show_last_recipes_once"] = True' not in source:
        source = replace_once(
            source,
            old_recipe_state,
            new_recipe_state,
            "recipe replay state block",
        )

    old_recipe_result = '''        if result:
            _, _, response = result
            show_recipes(response, profile, show_images=generate_recipe_images)
'''
    replay_block = '''        if result:
            # Rerun once so the top saved-inventory section is refreshed before recipes.
            st.rerun()

# Replay successful actions after the refresh without repeating any model calls.
if st.session_state.get("show_last_analysis_once", False):
    st.session_state["show_last_analysis_once"] = False
    parse_result = restore_manual_parse_result(
        st.session_state.get("last_manual_parse_result")
    )
    if parse_result is not None:
        show_manual_feedback(parse_result)

    update_payload = st.session_state.get("last_update")
    if isinstance(update_payload, dict):
        restored_update = InventoryUpdateResult.model_validate(update_payload)
        show_inventory_update(restored_update)
        show_inventory(restored_update.inventory, title="Alimentos detectados")
    elif remember_fridge and get_inventory():
        st.info("No se han introducido alimentos nuevos. Mantengo la nevera guardada tal como estaba.")
        show_inventory(
            get_inventory(),
            title="Alimentos guardados actualmente",
            editable=True,
            widget_namespace="saved_inventory_analysis_result",
        )

if st.session_state.get("show_last_recipes_once", False):
    st.session_state["show_last_recipes_once"] = False
    recipe_payload = st.session_state.get("last_recipes")
    if isinstance(recipe_payload, dict):
        restored_response = RecipeResponse.model_validate(recipe_payload)
        show_recipes(
            restored_response,
            profile,
            show_images=bool(st.session_state.get("last_recipe_images_enabled", False)),
        )
'''
    if "# Replay successful actions after the refresh" not in source:
        source = replace_once(
            source,
            old_recipe_result,
            replay_block,
            "successful recipe result block",
        )

    # Streamlit removed the legacy argument in favour of the explicit width API.
    source = source.replace('use_container_width=True', 'width="stretch"')
    source = source.replace('use_container_width=False', 'width="content"')
    return source


def _patch_recipe_images(source: str) -> str:
    """Use supported Gemini image models and guarantee a local visual fallback."""
    if "from src.fridgechef.local_recipe_image import generate_local_recipe_image" not in source:
        source = replace_once(
            source,
            "from src.fridgechef.llm_client import get_client\n",
            "from src.fridgechef.llm_client import get_client\n"
            "from src.fridgechef.local_recipe_image import generate_local_recipe_image\n",
            "local recipe image import",
        )

    source = source.replace(
        'DEFAULT_GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"',
        'DEFAULT_GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"',
    )

    ordered_models = '''def _ordered_image_models(settings) -> list[str]:
    """Use only current Gemini image endpoints and ignore retired Imagen models."""
    configured = [getattr(settings, "image_model_name", "")]
    configured.extend(
        part.strip()
        for part in getattr(settings, "image_fallback_models", "").split(",")
        if part.strip()
    )
    configured.extend([DEFAULT_GEMINI_IMAGE_MODEL, "gemini-2.5-flash-image"])

    models: list[str] = []
    for model_name in configured:
        clean = str(model_name or "").strip()
        if not clean.startswith("gemini-") or "image" not in clean:
            continue
        if clean not in models:
            models.append(clean)
    return models
'''
    source = replace_regex_once(
        source,
        r"def _ordered_image_models\(settings\) -> list\[str\]:.*?(?=\n\ndef _try_generate_image)",
        ordered_models.rstrip(),
        "ordered image model function",
    )

    try_generate = '''def _try_generate_image(prompt: str, settings) -> tuple[bytes, str, str]:
    """Try current Gemini image models through the retry-enabled global endpoint."""
    errors: list[str] = []
    location = "global"

    for model_name in _ordered_image_models(settings):
        try:
            image_bytes, mime_type = _generate_image_with_gemini_content(
                prompt,
                model_name,
                location,
                settings,
            )
            if image_bytes:
                return image_bytes, mime_type, model_name
        except Exception as exc:
            summary = " ".join(str(exc).split())[:280]
            errors.append(f"{model_name}: {type(exc).__name__}: {summary}")
            _LOGGER.warning(
                "Recipe image cloud attempt failed for %s: %s: %s",
                model_name,
                type(exc).__name__,
                summary,
            )

    raise RecipeImageGenerationError(
        " | ".join(errors) or "No current Gemini image model completed the request."
    )
'''
    source = replace_regex_once(
        source,
        r"def _try_generate_image\(prompt: str, settings\) -> tuple\[bytes, str, str\]:.*?(?=\n\ndef generate_recipe_image)",
        try_generate.rstrip(),
        "recipe image strategy function",
    )

    old_failure = '''    try:
        image_bytes, mime_type, used_model = _try_generate_image(prompt, settings)
    except Exception as exc:
        _LOGGER.exception("No se ha podido generar la imagen de receta '%s': %s", recipe.title, exc)
        return recipe.model_copy(
            update={
                "image_prompt": prompt,
                "image_generation_error": "No se ha podido generar la imagen de esta receta ahora mismo.",
            }
        )
'''
    new_failure = '''    try:
        image_bytes, mime_type, used_model = _try_generate_image(prompt, settings)
    except Exception as exc:
        # A local card keeps the one-image-per-recipe contract during cloud outages.
        summary = " ".join(str(exc).split())[:280]
        _LOGGER.warning(
            "Cloud recipe image unavailable for '%s'; using local fallback: %s",
            recipe.title,
            summary,
        )
        image_bytes, mime_type = generate_local_recipe_image(recipe)
        used_model = "local-recipe-card-v1"
'''
    if 'used_model = "local-recipe-card-v1"' not in source:
        source = replace_once(
            source,
            old_failure,
            new_failure,
            "recipe image fallback block",
        )
    return source


def apply() -> None:
    """Apply all production fixes idempotently and fail on unexpected source drift."""
    app_source = APP_PATH.read_text(encoding="utf-8")
    patched_app = _patch_app(app_source)
    if patched_app != app_source:
        APP_PATH.write_text(patched_app, encoding="utf-8")

    recipe_source = RECIPE_IMAGES_PATH.read_text(encoding="utf-8")
    patched_recipe_source = _patch_recipe_images(recipe_source)
    if patched_recipe_source != recipe_source:
        RECIPE_IMAGES_PATH.write_text(patched_recipe_source, encoding="utf-8")


if __name__ == "__main__":
    apply()
