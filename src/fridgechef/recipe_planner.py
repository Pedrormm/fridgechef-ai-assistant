from __future__ import annotations

import html
import re

try:
    from google.genai import types
except Exception:  # pragma: no cover - allows local tests without cloud SDKs
    types = None

from src.fridgechef.availability import (
    IngredientReadiness,
    assess_recipe_readiness,
    build_no_recipe_response,
    remove_invalid_recipes,
    unique_clean,
)
from src.fridgechef.config import get_settings
from src.fridgechef.food_name_normalizer import sanitize_recipe_response
from src.fridgechef.json_utils import extract_json_object
from src.fridgechef.llm_client import get_client
from src.fridgechef.models import FridgeAnalysis, RecipeItem, RecipeResponse, UserProfile
from src.fridgechef.policy import blocked_terms_for_profile, mark_policy_status, validate_recipe_response
from src.fridgechef.spanish_guard import ensure_recipe_response_spanish

RECIPE_PROMPT = """
You are FridgeChef AI Assistant, a practical cooking assistant.

Internal workflow to follow:
- Understand the available ingredients.
- Discard anything marked as possible_spoiled.
- Respect allergies, intolerances, diet and dislikes.
- Generate recipes that fit the requested maximum time and servings.
- Generate no more recipes than the number requested by the user.
- Generate fewer recipes when there are not enough ingredients to make more realistic options.
- Suggest a shopping_list only for optional or missing items, never as if they were already available.
- Keep the final wording friendly, clear and grammatically correct Spanish from Spain.

Strict rules:
- Do not invent available ingredients.
- ingredients_used must only contain items from AVAILABLE INGREDIENTS.
- Never include brands, manufacturers, supermarkets, product ranges, slogans or packaging claims in recipe titles, descriptions, ingredients, steps or shopping lists.
- AVAILABLE INGREDIENTS are culinary names; keep their useful food descriptors but do not reintroduce commercial wording.
- Do not use risky or possibly spoiled items.
- Respect the user's allergies, intolerances, diet, dislikes and custom preferences by semantic reasoning.
- Each recipe must include a short description, useful recipe information, ingredients and clear ordered steps.
- Do not return HTML, Markdown tables, XML, code blocks or CSS.
- Return only valid JSON.
"""

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def clean_user_text(value: object, fallback: str = "") -> str:
    """Return display-safe plain text for model output and stored notes.

    LLMs occasionally return small HTML fragments when asked for rich output.
    The frontend renders recipe and inventory content with normal Streamlit text
    widgets, so this cleanup keeps technical markup away from the user without
    altering the meaning of the message.
    """
    text = html.unescape(str(value or fallback))
    text = _TAG_RE.sub(" ", text)
    text = text.replace("```", " ").replace("###", " ")
    return _SPACE_RE.sub(" ", text).strip() or fallback


def sentence_case(value: object) -> str:
    """Capitalize the first visible character while preserving ingredient wording."""
    text = clean_user_text(value)
    if not text:
        return text
    return text[0].upper() + text[1:]


def _join_ingredients(items: list[str], limit: int | None = None) -> str:
    """Return a natural Spanish list without altering ingredient names."""
    selected = items[:limit] if limit else items
    if not selected:
        return "los alimentos disponibles"
    if len(selected) == 1:
        return selected[0]
    return ", ".join(selected[:-1]) + " y " + selected[-1]


def _requested_recipe_count(profile: UserProfile) -> int:
    """Clamp the requested number of recipes to the range exposed in the UI."""
    return max(1, min(5, int(getattr(profile, "recipe_count", 2) or 2)))


def _estimate_recipe_capacity(ingredients: list[str], requested_count: int) -> int:
    """Estimate how many genuinely different recipe ideas can be suggested.

    The estimate is intentionally conservative. It prevents the local fallback
    and post-generation guardrail from presenting five almost identical ideas
    when the fridge only contains two or three foods.
    """
    count = len(unique_clean(ingredients))
    if count <= 0:
        return 0
    if count <= 2:
        return min(requested_count, 1)
    if count <= 5:
        return min(requested_count, 2)
    if count <= 8:
        return min(requested_count, 3)
    return min(requested_count, 5)


def _split_time(total_minutes: int) -> tuple[int, int]:
    """Return preparation and cooking estimates that add up to the total time."""
    total = max(5, int(total_minutes or 30))
    prep = max(5, min(total - 1, round(total * 0.35))) if total > 5 else total
    cook = max(0, total - prep)
    return prep, cook


def _recipe_notice(requested: int, generated: int, ingredients: list[str]) -> str:
    """Explain politely when fewer recipes are generated than requested."""
    if generated >= requested:
        return ""
    return (
        f"Con los alimentos disponibles puedo preparar {generated} receta"
        f"{'s' if generated != 1 else ''} bien planteada"
        f"{'s' if generated != 1 else ''}. Para generar {requested}, necesitaría algún alimento más."
    )


def _fallback_title(index: int, ingredients: list[str]) -> str:
    """Create clear titles for local safe fallback recipes."""
    names = _join_ingredients(ingredients[:3])
    if index == 1:
        return f"Salteado sencillo de {names}"
    if index == 2:
        return f"Plato templado con {names}"
    if index == 3:
        return f"Combinado rápido de {names}"
    if index == 4:
        return f"Bowl casero con {names}"
    return f"Cena de aprovechamiento con {names}"


def _local_recipe_fallback(readiness: IngredientReadiness, profile: UserProfile) -> RecipeResponse:
    """Create safe recipe cards when the model call cannot be completed.

    The fallback never adds pantry ingredients to `ingredients_used`. It only uses
    the validated ingredients that passed the readiness step, which prevents the
    UI from failing with a generic error when the model/API is temporarily not
    available during a local demo.
    """
    ingredients = unique_clean(readiness.usable_ingredients)
    if not ingredients:
        return build_no_recipe_response(readiness)

    requested = _requested_recipe_count(profile)
    allowed = _estimate_recipe_capacity(ingredients, requested)
    time_limit = max(10, int(profile.time_limit_min or 30))
    servings = max(1, int(profile.servings or 1))
    recipes: list[RecipeItem] = []

    for index in range(allowed):
        # Rotate the ingredients so fallback ideas do not look identical while
        # still using only foods confirmed as available.
        rotated = ingredients[index:] + ingredients[:index]
        used = rotated[: min(len(rotated), max(2, min(4, len(rotated))))]
        prep, cook = _split_time(min(time_limit, 20 + index * 5))
        recipes.append(
            RecipeItem(
                title=_fallback_title(index + 1, used),
                description=(
                    f"Una propuesta sencilla para {servings} ración{'es' if servings != 1 else ''}, "
                    f"preparada con los alimentos que se han reconocido en tu nevera."
                ),
                why_this_recipe=(
                    "Encaja porque usa solo alimentos disponibles y mantiene la preparación dentro "
                    f"del límite aproximado de {time_limit} minutos."
                ),
                time_min=prep + cook,
                prep_time_min=prep,
                cook_time_min=cook,
                servings=servings,
                category="Plato principal",
                cuisine="Casera",
                ingredients_used=used,
                steps=[
                    "Lava y revisa los alimentos que lo necesiten antes de empezar.",
                    "Corta los ingredientes en trozos parecidos para que se cocinen de forma uniforme.",
                    "Cocina primero los alimentos que necesitan más tiempo y añade después los más delicados.",
                    "Sirve cuando todo esté en su punto y ajusta con básicos de despensa solo si los tienes.",
                ],
                anti_waste_tip="Guarda las sobras en un recipiente cerrado y consúmelas cuanto antes.",
                nutrition_notes=[],
                shopping_list=[],
                policy_status="local_fallback",
            )
        )

    notice = _recipe_notice(requested, len(recipes), ingredients)
    return RecipeResponse(
        recipes=recipes,
        global_explanation=notice or "He preparado recetas sencillas usando únicamente alimentos reconocidos en tu nevera.",
        safety_notes=["Propuesta revisada para no añadir ingredientes que no aparezcan como disponibles."],
        save_recommendation="Puedes guardar el inventario para seguir generando ideas más adelante.",
        raw_agent_notes={
            "recipe_generation": "local_safe_fallback",
            "requested_recipe_count": requested,
            "generated_recipe_count": len(recipes),
        },
        can_generate_recipes=bool(recipes),
        no_recipe_reason="",
        recognized_ingredients=readiness.recognized_items,
    )


def _generate_with_model(readiness: IngredientReadiness, manual_ingredients: list[str], profile: UserProfile, fridge_analysis: FridgeAnalysis | None) -> RecipeResponse:
    """Call Gemini and validate the structured recipe response."""
    if types is None:
        raise RuntimeError("google-genai types are not available in this environment.")

    settings = get_settings()
    client = get_client()
    blocked = sorted(blocked_terms_for_profile(profile))
    requested = _requested_recipe_count(profile)
    capacity = _estimate_recipe_capacity(readiness.usable_ingredients, requested)

    prompt = f"""
{RECIPE_PROMPT}

AVAILABLE INGREDIENTS:
{readiness.usable_ingredients}

RECOGNIZED ITEMS SHOWN TO THE USER:
{readiness.recognized_items}

MANUAL INGREDIENTS:
{manual_ingredients}

IMAGE ANALYSIS:
{fridge_analysis.model_dump() if fridge_analysis else {}}

USER PROFILE:
{profile.model_dump()}

REQUESTED NUMBER OF RECIPES:
{requested}

MAXIMUM SAFE NUMBER OF RECIPES WITH CURRENT INGREDIENTS:
{capacity}

BLOCKED TERMS:
{blocked}

Required JSON shape:
{{
  "recipes": [
    {{
      "title": "string",
      "description": "short Spanish description",
      "why_this_recipe": "string",
      "time_min": 0,
      "prep_time_min": 0,
      "cook_time_min": 0,
      "servings": {profile.servings},
      "category": "plato principal | cena ligera | entrante | aprovechamiento",
      "cuisine": "casera | mediterránea | internacional | other",
      "calories_per_serving": null,
      "ingredients_used": ["only available ingredient names"],
      "missing_required_for_target": ["string"],
      "missing_optional": ["string"],
      "steps": ["clear ordered cooking step"],
      "anti_waste_tip": "short useful tip",
      "allergen_alerts": ["string"],
      "nutrition_notes": [],
      "shopping_list": ["optional items only"],
      "policy_status": "unchecked"
    }}
  ],
  "global_explanation": "friendly Spanish explanation, including why fewer recipes were generated if applicable",
  "safety_notes": ["string"],
  "save_recommendation": "string",
  "raw_agent_notes": {{}},
  "can_generate_recipes": true,
  "no_recipe_reason": "",
  "recognized_ingredients": {readiness.recognized_items}
}}
"""

    response = client.models.generate_content(
        model=settings.model_name,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.1, response_mime_type="application/json"),
    )

    data = extract_json_object(response.text)
    recipe_response = RecipeResponse.model_validate(data)
    recipe_response = ensure_recipe_response_spanish(recipe_response)
    recipe_response.recognized_ingredients = readiness.recognized_items
    recipe_response.can_generate_recipes = bool(recipe_response.recipes)
    return recipe_response


def _clean_recipe(recipe: RecipeItem, profile: UserProfile) -> RecipeItem:
    """Normalize one recipe before it reaches the UI."""
    prep, cook = _split_time(recipe.time_min)
    steps = [sentence_case(step).rstrip(".") + "." for step in recipe.steps if clean_user_text(step)]
    if not steps:
        steps = [
            "Prepara y revisa los ingredientes disponibles.",
            "Cocina los alimentos según el tiempo que necesite cada uno.",
            "Sirve cuando esté listo y ajusta al gusto solo con básicos que ya tengas.",
        ]

    return recipe.model_copy(
        update={
            "title": sentence_case(recipe.title),
            "description": sentence_case(recipe.description),
            "why_this_recipe": sentence_case(recipe.why_this_recipe),
            "time_min": max(5, min(int(recipe.time_min or profile.time_limit_min), int(profile.time_limit_min or 90))),
            "prep_time_min": recipe.prep_time_min or prep,
            "cook_time_min": recipe.cook_time_min if recipe.cook_time_min is not None else cook,
            "servings": recipe.servings or profile.servings,
            "category": sentence_case(recipe.category or "Plato principal"),
            "cuisine": sentence_case(recipe.cuisine or "Casera"),
            "ingredients_used": [sentence_case(item) for item in unique_clean(recipe.ingredients_used)],
            "missing_required_for_target": [sentence_case(item) for item in unique_clean(recipe.missing_required_for_target)],
            "missing_optional": [sentence_case(item) for item in unique_clean(recipe.missing_optional)],
            "steps": steps,
            "anti_waste_tip": sentence_case(recipe.anti_waste_tip or "Aprovecha primero los alimentos más maduros."),
            "allergen_alerts": [sentence_case(note) for note in recipe.allergen_alerts],
            "nutrition_notes": [sentence_case(note) for note in recipe.nutrition_notes if clean_user_text(note)],
            "shopping_list": [sentence_case(item) for item in unique_clean(recipe.shopping_list)],
        }
    )


def post_process_recipe_response(response: RecipeResponse, readiness: IngredientReadiness, profile: UserProfile) -> RecipeResponse:
    """Final recipe callback before rendering.

    This guardrail keeps the UI clean, limits the number of cards, removes model
    markup, and adds a friendly explanation when fewer recipes are possible than
    the number requested by the user.
    """
    requested = _requested_recipe_count(profile)
    capacity = _estimate_recipe_capacity(readiness.usable_ingredients, requested)
    response.recipes = [_clean_recipe(recipe, profile) for recipe in response.recipes[:capacity]]
    generated = len(response.recipes)

    notice = _recipe_notice(requested, generated, readiness.usable_ingredients) if generated else ""
    explanation = sentence_case(response.global_explanation or "")
    if notice and notice not in explanation:
        explanation = notice

    response.global_explanation = explanation or "He preparado recetas con los alimentos disponibles."
    response.save_recommendation = sentence_case(response.save_recommendation)
    response.safety_notes = [sentence_case(note) for note in response.safety_notes]
    response.raw_agent_notes["requested_recipe_count"] = requested
    response.raw_agent_notes["generated_recipe_count"] = generated
    response.can_generate_recipes = bool(response.recipes)
    return response


def generate_recipes(
    manual_ingredients: list[str],
    profile: UserProfile,
    fridge_analysis: FridgeAnalysis | None,
) -> RecipeResponse:
    """Generate recipe suggestions from validated fridge ingredients.

    The recipe-readiness step runs before generation so the model does not receive
    unusable input such as water-only photos, packaging or doubtful image items.
    The post-processing callback runs after generation to prevent invented items,
    excess recipes, HTML snippets or unfriendly text from reaching the interface.
    """
    readiness = assess_recipe_readiness(manual_ingredients, fridge_analysis)
    if not readiness.can_generate:
        return build_no_recipe_response(readiness)

    try:
        recipe_response = _generate_with_model(readiness, manual_ingredients, profile, fridge_analysis)
    except Exception:
        recipe_response = _local_recipe_fallback(readiness, profile)

    # Final output callback removes any commercial token the model could
    # have echoed despite receiving brand-free input. This runs before the
    # availability guard so ingredient comparisons use the same canonical names.
    recipe_response = sanitize_recipe_response(recipe_response)
    recipe_response, availability_warnings = remove_invalid_recipes(recipe_response, readiness.usable_ingredients)
    if availability_warnings and not recipe_response.recipes:
        fallback = build_no_recipe_response(readiness)
        fallback.safety_notes.extend(availability_warnings)
        return fallback

    recipe_response = ensure_recipe_response_spanish(recipe_response)
    recipe_response = mark_policy_status(recipe_response, profile)
    violations = validate_recipe_response(recipe_response, profile)
    if violations:
        recipe_response.safety_notes.extend(["Revisión local: " + violation for violation in violations])

    if not recipe_response.recipes:
        return build_no_recipe_response(readiness)

    return ensure_recipe_response_spanish(post_process_recipe_response(recipe_response, readiness, profile))
