from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Iterable

from src.fridgechef.models import FridgeAnalysis, RecipeItem, RecipeResponse


@dataclass(frozen=True)
class IngredientReadiness:
    """Small deterministic decision used before asking the model for recipes."""

    can_generate: bool
    usable_ingredients: list[str]
    recognized_items: list[str]
    reason: str


NON_RECIPE_ITEMS = {
    "agua",
    "water",
    "botella",
    "botellas",
    "bottle",
    "bottles",
    "envase",
    "envases",
    "container",
    "containers",
    "liquido",
    "liquidos",
    "liquid",
    "liquids",
    "liquido sin identificar",
    "liquidos sin identificar",
    "unidentified liquid",
    "unidentified liquids",
    "drink",
    "drinks",
    "bebida",
    "bebidas",
    "hielo",
    "ice",
    "empty bottle",
    "empty bottles",
    "botella vacia",
    "botellas vacias",
}

SPOILED_STATES = {"possible_spoiled", "spoiled"}


def normalize_text(value: str) -> str:
    """Normalize text so Spanish accents and casing do not break comparisons."""
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(normalized.lower().strip().split())


def unique_clean(items: Iterable[str]) -> list[str]:
    """Return unique values while preserving the original order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        clean = " ".join(str(item or "").strip().split())
        key = normalize_text(clean)
        if clean and key not in seen:
            result.append(clean)
            seen.add(key)
    return result


def is_non_recipe_item(name: str) -> bool:
    """Identify items that should be shown to the user but not used as recipe bases."""
    key = normalize_text(name)
    if not key:
        return True
    if key in NON_RECIPE_ITEMS:
        return True

    non_recipe_markers = {
        "agua",
        "water",
        "botella",
        "bottle",
        "envase",
        "container",
        "unidentified",
        "sin identificar",
        "empty bottle",
        "botella vacia",
    }
    return any(marker in key for marker in non_recipe_markers)


def recognized_items(manual_ingredients: list[str], analysis: FridgeAnalysis | None) -> list[str]:
    """Collect everything that can be displayed as recognized input."""
    items: list[str] = []
    items.extend(manual_ingredients)

    if analysis:
        items.extend(ingredient.name for ingredient in analysis.visible_ingredients if ingredient.name)
        items.extend(analysis.uncertain_items)
        for observation in analysis.barcode_observations:
            if observation.product_name_guess:
                items.append(observation.product_name_guess)

    return unique_clean(items)


def usable_recipe_ingredients(manual_ingredients: list[str], analysis: FridgeAnalysis | None) -> list[str]:
    """Collect ingredients that are safe enough to be offered to the recipe model."""
    usable: list[str] = []
    usable.extend(item for item in manual_ingredients if not is_non_recipe_item(item))

    if analysis:
        spoiled = {normalize_text(item.name) for item in analysis.possible_spoiled_items}
        for ingredient in analysis.visible_ingredients:
            name = ingredient.name
            if not name or is_non_recipe_item(name):
                continue
            if normalize_text(name) in spoiled or ingredient.state in SPOILED_STATES:
                continue
            usable.append(name)

    return unique_clean(usable)


def assess_recipe_readiness(manual_ingredients: list[str], analysis: FridgeAnalysis | None) -> IngredientReadiness:
    """Decide whether there is enough reliable input to request recipes."""
    recognized = recognized_items(manual_ingredients, analysis)
    usable = usable_recipe_ingredients(manual_ingredients, analysis)

    if not recognized:
        return IngredientReadiness(
            can_generate=False,
            usable_ingredients=[],
            recognized_items=[],
            reason="No he encontrado ingredientes claros todavía. Escribe alguno o sube una foto más cercana y con buena luz.",
        )

    if not usable:
        visible = ", ".join(recognized)
        return IngredientReadiness(
            can_generate=False,
            usable_ingredients=[],
            recognized_items=recognized,
            reason=(
                "He reconocido esto: " + visible + ". "
                "Con eso no puedo proponer recetas fiables sin inventar ingredientes. "
                "Añade algún alimento más o escribe ingredientes manualmente y lo intento de nuevo."
            ),
        )

    return IngredientReadiness(
        can_generate=True,
        usable_ingredients=usable,
        recognized_items=recognized,
        reason="Hay ingredientes suficientes para buscar recetas realistas.",
    )


def build_no_recipe_response(readiness: IngredientReadiness) -> RecipeResponse:
    """Create a friendly response when recipe generation should be skipped."""
    return RecipeResponse(
        recipes=[],
        global_explanation=readiness.reason,
        safety_notes=[
            "No se han generado recetas porque no hay suficientes alimentos claros para cocinar sin inventar ingredientes."
        ],
        save_recommendation="Puedes guardar el resultado si quieres conservar el análisis, pero no es necesario.",
        raw_agent_notes={"deterministic_guardrail": "insufficient_usable_ingredients"},
        can_generate_recipes=False,
        no_recipe_reason=readiness.reason,
        recognized_ingredients=readiness.recognized_items,
    )


def recipe_uses_only_available_items(recipe: RecipeItem, available: list[str]) -> tuple[bool, list[str]]:
    """Check that ingredients_used does not contain invented pantry items."""
    available_keys = {normalize_text(item) for item in available}
    invalid: list[str] = []

    for ingredient in recipe.ingredients_used:
        key = normalize_text(ingredient)
        if not key:
            continue
        exact_match = key in available_keys
        partial_match = any(key in available_key or available_key in key for available_key in available_keys)
        if not exact_match and not partial_match:
            invalid.append(ingredient)

    return not invalid, invalid


def remove_invalid_recipes(response: RecipeResponse, available: list[str]) -> tuple[RecipeResponse, list[str]]:
    """Drop recipes that claim to use ingredients not recognized as available."""
    kept: list[RecipeItem] = []
    warnings: list[str] = []

    for recipe in response.recipes:
        is_valid, invalid = recipe_uses_only_available_items(recipe, available)
        if is_valid:
            kept.append(recipe)
        else:
            warnings.append(
                f"Se ha descartado '{recipe.title}' porque incluía ingredientes no detectados como disponibles: {', '.join(invalid)}."
            )

    response.recipes = kept
    response.safety_notes.extend(warnings)
    return response, warnings
