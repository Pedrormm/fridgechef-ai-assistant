from __future__ import annotations

from pathlib import Path

from scripts.patch_utils import replace_once


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "streamlit_app" / "app.py"
INVENTORY = ROOT / "src" / "fridgechef" / "inventory.py"
RECIPE = ROOT / "src" / "fridgechef" / "recipe_planner.py"
VISION = ROOT / "src" / "fridgechef" / "vision.py"
TEXT = ROOT / "src" / "fridgechef" / "text_parser.py"
WORKFLOW = ROOT / ".github" / "workflows" / "apply-additive-multi-input.yml"


def _replace(source: str, old: str, new: str, description: str) -> str:
    """Apply one migration safely and allow repeated CI verification."""
    if new in source:
        return source
    return replace_once(source, old, new, description)


def _patch_app(source: str) -> str:
    source = _replace(
        source,
        "from src.fridgechef.fridge_qa import answer_fridge_question\n",
        "from src.fridgechef.fridge_qa import answer_fridge_question\n"
        "from src.fridgechef.food_name_normalizer import (\n"
        "    sanitize_action_inputs,\n"
        "    sanitize_inventory_items,\n"
        ")\n",
        "food-name normalizer import",
    )
    source = _replace(
        source,
        "    apply_inventory_update,\n    friendly_state_label,\n",
        "    apply_inventory_update,\n    consolidate_inventory,\n    friendly_state_label,\n",
        "inventory consolidation import",
    )
    source = _replace(
        source,
        '''    if is_new_browser_session and settings.allow_chat_persistence:\n        result = load_inventory_state()\n        st.session_state["fridge_inventory"] = result.inventory\n        _store_persistence_result(result)\n''',
        '''    if is_new_browser_session and settings.allow_chat_persistence:\n        result = load_inventory_state()\n        loaded_items = [InventoryItem.model_validate(item) for item in result.inventory]\n        cleaned_items, _ = sanitize_inventory_items(loaded_items)\n        cleaned_items = consolidate_inventory(cleaned_items, quantity_mode="max")\n        cleaned_payload = [item.model_dump() for item in cleaned_items]\n        st.session_state["fridge_inventory"] = cleaned_payload\n\n        # Migrate legacy branded rows once. The normalizer caches decisions in the\n        # same SQLite database, so later browser sessions do not consume quota.\n        if cleaned_payload != result.inventory:\n            _store_persistence_result(save_inventory_state(cleaned_payload))\n        else:\n            _store_persistence_result(result)\n''',
        "legacy inventory migration",
    )
    source = _replace(
        source,
        '''    incoming_items = build_incoming_inventory(\n        parse_result.accepted_items,\n        image_results,\n    )\n''',
        '''    # Run the dedicated commercial-name sub-agent once for the complete\n    # action batch. Both Analyze and Generate Recipes use this function, so text,\n    # uploaded photos and camera photos follow the same validated normalization.\n    parse_result, image_results, _ = sanitize_action_inputs(\n        parse_result,\n        image_results,\n    )\n\n    incoming_items = build_incoming_inventory(\n        parse_result.accepted_items,\n        image_results,\n    )\n''',
        "action input normalizer",
    )
    return source


def _patch_inventory(source: str) -> str:
    source = _replace(
        source,
        "from src.fridgechef.availability import normalize_text, unique_clean\n",
        "from src.fridgechef.availability import normalize_text, unique_clean\n"
        "from src.fridgechef.food_name_normalizer import strip_commercial_terms\n",
        "inventory brand guard import",
    )
    source = _replace(
        source,
        '''def item_to_recipe_name(item: InventoryItem) -> str:\n    """Return the clean ingredient name used by the recipe generator."""\n    return item.name\n''',
        '''def item_to_recipe_name(item: InventoryItem) -> str:\n    """Return a defensive brand-free ingredient name for recipe generation."""\n    return strip_commercial_terms(item.name)\n''',
        "recipe ingredient name guard",
    )
    return source


def _patch_recipe(source: str) -> str:
    source = _replace(
        source,
        "from src.fridgechef.config import get_settings\n",
        "from src.fridgechef.config import get_settings\n"
        "from src.fridgechef.food_name_normalizer import sanitize_recipe_response\n",
        "recipe normalizer import",
    )
    source = _replace(
        source,
        "- ingredients_used must only contain items from AVAILABLE INGREDIENTS.\n",
        "- ingredients_used must only contain items from AVAILABLE INGREDIENTS.\n"
        "- Never include brands, manufacturers, supermarkets, product ranges, slogans or packaging claims in recipe titles, descriptions, ingredients, steps or shopping lists.\n"
        "- AVAILABLE INGREDIENTS are culinary names; keep their useful food descriptors but do not reintroduce commercial wording.\n",
        "recipe commercial-name prompt rules",
    )
    source = _replace(
        source,
        '''    recipe_response, availability_warnings = remove_invalid_recipes(recipe_response, readiness.usable_ingredients)\n''',
        '''    # Final output callback removes any commercial token the model could\n    # have echoed despite receiving brand-free input. This runs before the\n    # availability guard so ingredient comparisons use the same canonical names.\n    recipe_response = sanitize_recipe_response(recipe_response)\n    recipe_response, availability_warnings = remove_invalid_recipes(recipe_response, readiness.usable_ingredients)\n''',
        "recipe output normalizer callback",
    )
    return source


def _patch_vision(source: str) -> str:
    return _replace(
        source,
        "- No inventes alimentos, cantidades, fechas ni marcas.\n",
        "- No inventes alimentos, cantidades, fechas ni marcas.\n"
        "- En name y product_name_guess devuelve el nombre culinario completo sin marcas, fabricantes, supermercados, gamas, eslóganes, tamaños de envase ni palabras promocionales.\n"
        "- Conserva detalles útiles como corte, animal, formato, preparación, ahumado, natural, extrafino y sabor.\n",
        "vision commercial-name prompt rules",
    )


def _patch_text(source: str) -> str:
    return _replace(
        source,
        "- Conserva el estado indicado por el usuario.\n",
        "- Conserva el estado indicado por el usuario.\n"
        "- Devuelve el nombre culinario completo sin marcas, fabricantes, supermercados, gamas comerciales, eslóganes, tamaños de envase ni palabras promocionales.\n"
        "- Conserva detalles útiles como corte, animal, formato, preparación, ahumado, natural, extrafino y sabor.\n",
        "manual commercial-name prompt rules",
    )


def _patch_workflow(source: str) -> str:
    return _replace(
        source,
        '''      - name: Verify collapsible recipe UI and recovered-provider logs\n        run: python -m scripts.patch_collapsible_ingredients_and_logs\n''',
        '''      - name: Verify collapsible recipe UI and recovered-provider logs\n        run: python -m scripts.patch_collapsible_ingredients_and_logs\n\n      - name: Verify brand-free food normalization\n        run: python -m scripts.patch_brand_free_food_names\n''',
        "CI brand-free verification step",
    )


def _write(path: Path, content: str) -> None:
    current = path.read_text(encoding="utf-8")
    if current != content:
        path.write_text(content, encoding="utf-8")


def apply() -> None:
    _write(APP, _patch_app(APP.read_text(encoding="utf-8")))
    _write(INVENTORY, _patch_inventory(INVENTORY.read_text(encoding="utf-8")))
    _write(RECIPE, _patch_recipe(RECIPE.read_text(encoding="utf-8")))
    _write(VISION, _patch_vision(VISION.read_text(encoding="utf-8")))
    _write(TEXT, _patch_text(TEXT.read_text(encoding="utf-8")))
    _write(WORKFLOW, _patch_workflow(WORKFLOW.read_text(encoding="utf-8")))


if __name__ == "__main__":
    apply()
