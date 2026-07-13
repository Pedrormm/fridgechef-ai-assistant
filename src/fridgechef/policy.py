from __future__ import annotations

import json
import unicodedata
from collections.abc import Callable

try:
    from google.genai import types
except Exception:  # pragma: no cover - optional during local unit tests
    types = None

from src.fridgechef.json_utils import extract_json_object
from src.fridgechef.models import RecipeItem, RecipeResponse, UserProfile

try:
    from src.fridgechef.config import get_settings
    from src.fridgechef.llm_client import get_client
except Exception:  # pragma: no cover
    get_settings = None
    get_client = None

PolicyAgent = Callable[[RecipeItem, UserProfile], list[str]]


def norm(text: str) -> str:
    """Normalize text so accents, casing and spacing do not break comparisons."""
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(normalized.lower().strip().split())


def _explicit_user_restrictions(profile: UserProfile) -> set[str]:
    """Return only restrictions directly selected or written by the user.

    This is not a food dictionary. It is the user's own input and is used as a
    safe local fallback when the semantic policy agent is unavailable.
    """
    raw_values = [
        *profile.allergies,
        *profile.intolerances,
        *profile.dislikes,
        *profile.custom_preferences.values(),
    ]
    return {norm(value) for value in raw_values if norm(value)}


def blocked_terms_for_profile(profile: UserProfile) -> set[str]:
    """Expose user-provided restrictions to the recipe prompt.

    The previous implementation expanded diet labels through static food lists.
    That has been replaced by semantic model instructions, so this function only
    returns values explicitly provided by the user.
    """
    return _explicit_user_restrictions(profile)


def _local_explicit_match_warnings(recipe: RecipeItem, profile: UserProfile) -> list[str]:
    """Detect direct matches against user-provided restrictions only."""
    warnings: list[str] = []
    restrictions = _explicit_user_restrictions(profile)
    if not restrictions:
        return warnings

    recipe_values = [*recipe.ingredients_used, *recipe.shopping_list, *recipe.missing_optional]
    for ingredient in recipe_values:
        ingredient_key = norm(ingredient)
        if not ingredient_key:
            continue
        matches = [term for term in restrictions if term in ingredient_key or ingredient_key in term]
        if matches:
            warnings.append(
                f"La receta '{recipe.title}' menciona '{ingredient}', que no encaja con una preferencia o restricción indicada."
            )
    return warnings


def _agent_policy_warnings(recipe: RecipeItem, profile: UserProfile) -> list[str]:
    """Ask a semantic guardrail agent to validate recipe restrictions."""
    if types is None or get_client is None or get_settings is None:
        return _local_explicit_match_warnings(recipe, profile)

    client = get_client()
    settings = get_settings()
    prompt = f"""
Eres el agente de seguridad alimentaria y preferencias de FridgeChef AI Assistant.

Tarea:
- Revisa si la receta contradice la dieta, alergias, intolerancias, alimentos evitados, objetivo o preferencias personalizadas del usuario.
- Decide por significado y contexto, no mediante listas fijas.
- No añadas datos ni cambies la receta.
- Si hay problemas, devuelve avisos breves y amables en español de España.
- Si no hay problemas, devuelve una lista vacía.
- Devuelve únicamente JSON válido.

Perfil del usuario:
{profile.model_dump_json(indent=2)}

Receta:
{recipe.model_dump_json(indent=2)}

Estructura obligatoria:
{{
  "warnings": ["aviso en español"]
}}
"""
    response = client.models.generate_content(
        model=settings.model_name,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json"),
    )
    data = extract_json_object(response.text or "")
    warnings = data.get("warnings", [])
    return [str(item).strip() for item in warnings if str(item).strip()]


def validate_recipe_item(recipe: RecipeItem, profile: UserProfile, policy_agent: PolicyAgent | None = None) -> list[str]:
    """Return friendly warnings for recipes that conflict with user restrictions."""
    if policy_agent:
        return policy_agent(recipe, profile)
    try:
        return _agent_policy_warnings(recipe, profile)
    except Exception:
        return _local_explicit_match_warnings(recipe, profile)


def validate_recipe_response(
    response: RecipeResponse,
    profile: UserProfile,
    policy_agent: PolicyAgent | None = None,
) -> list[str]:
    """Validate every recipe returned by the model."""
    warnings: list[str] = []
    for recipe in response.recipes:
        warnings.extend(validate_recipe_item(recipe, profile, policy_agent=policy_agent))
    return warnings


def mark_policy_status(response: RecipeResponse, profile: UserProfile) -> RecipeResponse:
    """Mark each recipe after semantic/local policy validation."""
    for recipe in response.recipes:
        recipe.policy_status = "blocked" if validate_recipe_item(recipe, profile) else "ok"
    return response
