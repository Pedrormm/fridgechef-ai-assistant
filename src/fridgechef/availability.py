from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from typing import Callable, Iterable

try:
    from google.genai import types
except Exception:  # pragma: no cover - allows local tests without google-genai installed
    types = None

from src.fridgechef.config import get_settings
from src.fridgechef.json_utils import extract_json_object
from src.fridgechef.llm_client import get_client
from src.fridgechef.models import FridgeAnalysis, IgnoredTextFragment, RecipeItem, RecipeReadinessAssessment, RecipeResponse
from src.fridgechef.spanish_guard import ensure_readiness_spanish


@dataclass(frozen=True)
class IngredientReadiness:
    """Decision used before asking the recipe model for suggestions."""

    can_generate: bool
    usable_ingredients: list[str]
    recognized_items: list[str]
    reason: str
    ignored_items: list[IgnoredTextFragment] | None = None
    used_agent: bool = False


ReadinessAgent = Callable[[list[str], FridgeAnalysis | None], RecipeReadinessAssessment]


def _is_risky_state(state: str) -> bool:
    """Return whether an internal freshness state should block cooking."""
    return state == "possible_spoiled" or state == "spoiled"


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


def _spoiled_item_names(analysis: FridgeAnalysis | None) -> set[str]:
    """Return image items that should never be used directly for recipes."""
    if not analysis:
        return set()
    values = {normalize_text(item.name) for item in analysis.possible_spoiled_items if item.name}
    values.update(
        normalize_text(item.name)
        for item in analysis.visible_ingredients
        if item.name and _is_risky_state(item.state)
    )
    return values


def _fallback_readiness(manual_ingredients: list[str], analysis: FridgeAnalysis | None) -> RecipeReadinessAssessment:
    """Conservative local fallback when the recipe-readiness agent is unavailable.

    Manual ingredients have already passed through the text-understanding agent or
    its conservative repair path, so they are safe enough to use as recipe input.
    Image-only input is more ambiguous; without the readiness agent, the safest
    behavior is to show what was recognized but not generate recipes from
    uncertain products.
    """
    recognized = recognized_items(manual_ingredients, analysis)
    spoiled = _spoiled_item_names(analysis)
    usable = unique_clean(
        item for item in manual_ingredients if item and normalize_text(item) not in spoiled
    )

    return RecipeReadinessAssessment(
        can_generate=bool(usable),
        usable_ingredients=usable,
        recognized_items=recognized,
        no_recipe_reason=(
            "He reconocido elementos en la imagen, pero necesito confirmar alimentos concretos antes de generar recetas. "
            "Puedes escribir los ingredientes visibles o volver a intentarlo con una foto más clara."
            if recognized and not usable
            else "No he podido confirmar alimentos suficientes para cocinar sin inventar ingredientes."
        ),
        reasoning_summary="Decisión local conservadora usada porque el agente de disponibilidad no estaba disponible.",
    )


def _run_recipe_readiness_agent(manual_ingredients: list[str], analysis: FridgeAnalysis | None) -> RecipeReadinessAssessment:
    """Use Gemini as a dedicated sub-agent to decide whether recipes are possible.

    This replaces local word lists with a language-understanding decision. The
    agent sees recognized items and image metadata, then decides if the available
    items are usable food ingredients, uncertain products, non-cooking items or
    risky food.
    """
    client = get_client()
    settings = get_settings()
    recognized = recognized_items(manual_ingredients, analysis)
    spoiled = list(_spoiled_item_names(analysis))

    prompt = f"""
You are the recipe-readiness sub-agent for FridgeChef AI Assistant.

Goal:
Decide whether the recognized fridge input contains enough usable food to generate recipes.

Rules:
- Use semantic understanding, not a static word list.
- Do not invent ingredients.
- Recognized elements that are not enough for cooking can be shown to the user, but they must not be used for recipes.
- Risky or possibly spoiled items must not be used for recipes.
- If there are usable ingredients, return only those ingredients in usable_ingredients.
- If there are no usable ingredients, explain kindly in Spanish.
- Every visible text value must be Spanish from Spain.
- Return valid JSON only.

Manual ingredients already extracted by the text agent:
{json.dumps(manual_ingredients, ensure_ascii=False, indent=2)}

Image analysis:
{analysis.model_dump_json(indent=2) if analysis else "{}"}

Recognized items shown to the user:
{json.dumps(recognized, ensure_ascii=False, indent=2)}

Items marked as spoiled or risky:
{json.dumps(spoiled, ensure_ascii=False, indent=2)}

Required JSON shape:
{{
  "can_generate": true,
  "usable_ingredients": ["ingredient names safe enough to cook with"],
  "recognized_items": ["all recognized items worth showing to the user"],
  "no_recipe_reason": "friendly Spanish explanation if can_generate is false",
  "ignored_items": [{{"text": "recognized but unusable item", "reason": "friendly Spanish reason"}}],
  "reasoning_summary": "short Spanish explanation"
}}
"""
    response = client.models.generate_content(
        model=settings.model_name,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json"),
    )
    data = extract_json_object(response.text)
    assessment = RecipeReadinessAssessment.model_validate(data)
    return ensure_readiness_spanish(assessment)


def assess_recipe_readiness(
    manual_ingredients: list[str],
    analysis: FridgeAnalysis | None,
    readiness_agent: ReadinessAgent | None = None,
) -> IngredientReadiness:
    """Decide whether there is enough reliable input to request recipes."""
    recognized = recognized_items(manual_ingredients, analysis)
    if not recognized:
        return IngredientReadiness(
            can_generate=False,
            usable_ingredients=[],
            recognized_items=[],
            reason="No he encontrado ingredientes claros todavía. Escribe alguno o sube una foto más cercana y con buena luz.",
            ignored_items=[],
            used_agent=False,
        )

    try:
        assessment = readiness_agent(manual_ingredients, analysis) if readiness_agent else _run_recipe_readiness_agent(manual_ingredients, analysis)
        assessment = ensure_readiness_spanish(assessment)
        used_agent = True
    except Exception:
        assessment = _fallback_readiness(manual_ingredients, analysis)
        used_agent = False

    usable = unique_clean(assessment.usable_ingredients)
    recognized_from_agent = unique_clean(assessment.recognized_items or recognized)
    can_generate = bool(assessment.can_generate and usable)

    if not can_generate:
        visible = ", ".join(recognized_from_agent)
        reason = assessment.no_recipe_reason or (
            "He reconocido esto: " + visible + ". "
            "Con eso no puedo proponer recetas fiables sin inventar ingredientes. "
            "Añade algún alimento más o escribe ingredientes manualmente y lo intento de nuevo."
        )
        return IngredientReadiness(
            can_generate=False,
            usable_ingredients=[],
            recognized_items=recognized_from_agent,
            reason=reason,
            ignored_items=assessment.ignored_items,
            used_agent=used_agent,
        )

    return IngredientReadiness(
        can_generate=True,
        usable_ingredients=usable,
        recognized_items=recognized_from_agent,
        reason="Hay ingredientes suficientes para buscar recetas realistas.",
        ignored_items=assessment.ignored_items,
        used_agent=used_agent,
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
        raw_agent_notes={
            "readiness_agent": "blocked_recipe_generation",
            "used_agent": readiness.used_agent,
        },
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
