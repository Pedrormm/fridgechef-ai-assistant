from __future__ import annotations

import unicodedata
from collections.abc import Iterable

from src.fridgechef.models import RecipeItem, RecipeResponse, UserProfile


def norm(text: str) -> str:
    """Normalize text so guardrails work with accents, casing and spacing."""
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(normalized.lower().strip().split())


VEGAN_FORBIDDEN = {
    "carne", "pollo", "pavo", "cerdo", "ternera", "bacon", "jamon", "chorizo",
    "pescado", "atun", "salmon", "merluza", "bacalao", "marisco", "gamba", "langostino",
    "huevo", "huevos", "leche", "queso", "yogur", "yogurt", "mantequilla", "nata", "miel",
}

VEGETARIAN_FORBIDDEN = {
    "carne", "pollo", "pavo", "cerdo", "ternera", "bacon", "jamon", "chorizo",
    "pescado", "atun", "salmon", "merluza", "bacalao", "marisco", "gamba", "langostino",
}

LACTOSE_FORBIDDEN = {"leche", "queso", "yogur", "yogurt", "nata", "mantequilla", "lactosa", "bechamel"}
GLUTEN_FORBIDDEN = {"gluten", "trigo", "cebada", "centeno", "harina", "pan", "pasta", "seitan"}


def _contains_any(ingredient: str, blocked: Iterable[str]) -> set[str]:
    normalized = norm(ingredient)
    return {term for term in blocked if term in normalized or normalized in term}


def blocked_terms_for_profile(profile: UserProfile) -> set[str]:
    """Build a deterministic deny-list from user restrictions."""
    blocked = {norm(item) for item in profile.allergies + profile.intolerances if item}
    diet = {norm(item) for item in profile.diet}
    intolerances = {norm(item) for item in profile.intolerances}

    if {"vegana", "vegano", "vegan"} & diet:
        blocked |= VEGAN_FORBIDDEN
    if {"vegetariana", "vegetariano", "vegetarian"} & diet:
        blocked |= VEGETARIAN_FORBIDDEN
    if "sin lactosa" in diet or "lactosa" in intolerances or "intolerancia lactosa" in intolerances:
        blocked |= LACTOSE_FORBIDDEN
    if "sin gluten" in diet or "gluten" in intolerances or "celiaca" in diet or "celiaco" in diet:
        blocked |= GLUTEN_FORBIDDEN

    return blocked


def validate_recipe_item(recipe: RecipeItem, profile: UserProfile) -> list[str]:
    """Return friendly warnings for recipes that conflict with user restrictions."""
    warnings: list[str] = []
    blocked = blocked_terms_for_profile(profile)

    for ingredient in recipe.ingredients_used + recipe.shopping_list + recipe.missing_optional:
        hits = _contains_any(ingredient, blocked)
        if hits:
            warnings.append(
                f"La receta '{recipe.title}' menciona '{ingredient}', que no encaja con estas restricciones: {', '.join(sorted(hits))}."
            )

    return warnings


def validate_recipe_response(response: RecipeResponse, profile: UserProfile) -> list[str]:
    """Validate every recipe returned by the model."""
    warnings: list[str] = []
    for recipe in response.recipes:
        warnings.extend(validate_recipe_item(recipe, profile))
    return warnings


def mark_policy_status(response: RecipeResponse, profile: UserProfile) -> RecipeResponse:
    """Mark each recipe as safe or blocked after deterministic validation."""
    for recipe in response.recipes:
        recipe.policy_status = "blocked" if validate_recipe_item(recipe, profile) else "ok"
    return response
