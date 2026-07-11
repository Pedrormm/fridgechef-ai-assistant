from __future__ import annotations

from google.genai import types

from src.fridgechef.availability import (
    assess_recipe_readiness,
    build_no_recipe_response,
    remove_invalid_recipes,
)
from src.fridgechef.config import get_settings
from src.fridgechef.json_utils import extract_json_object
from src.fridgechef.llm_client import get_client
from src.fridgechef.models import FridgeAnalysis, RecipeResponse, UserProfile
from src.fridgechef.policy import blocked_terms_for_profile, mark_policy_status, validate_recipe_response

RECIPE_PROMPT = """
You are FridgeChef AI, a practical cooking assistant.

Internal workflow to follow:
- Understand the available ingredients.
- Discard anything marked as possible_spoiled.
- Respect allergies, intolerances, diet and dislikes.
- Prefer simple recipes that fit the requested time and servings.
- Suggest a shopping_list only for optional or missing items, never as if they were already available.
- Keep the final wording friendly and easy to understand.

Strict rules:
- Generate up to 3 recipes only when the available ingredients make that realistic.
- Do not invent available ingredients.
- ingredients_used must only contain items from AVAILABLE INGREDIENTS.
- Do not use possible_spoiled_items.
- Respect blocked terms from allergies, intolerances and diet.
- If the user is vegan, do not use meat, fish, eggs, dairy, honey or animal derivatives.
- If the user is lactose intolerant, do not use milk, cheese, cream, yogurt, butter or lactose.
- If the user avoids gluten, do not use wheat, normal bread, normal pasta, flour, barley, rye or gluten.
- Each recipe must explain why it fits the user.
- Each recipe must include clear steps.
- Each recipe must include one anti-waste tip.
- Return only valid JSON.
"""


def generate_recipes(
    manual_ingredients: list[str],
    profile: UserProfile,
    fridge_analysis: FridgeAnalysis | None,
) -> RecipeResponse:
    """Generate recipes only when deterministic checks show enough reliable input."""
    readiness = assess_recipe_readiness(manual_ingredients, fridge_analysis)
    if not readiness.can_generate:
        return build_no_recipe_response(readiness)

    settings = get_settings()
    client = get_client()
    blocked = sorted(blocked_terms_for_profile(profile))

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

BLOCKED TERMS:
{blocked}

Required JSON shape:
{{
  "recipes": [
    {{
      "title": "string",
      "description": "string",
      "why_this_recipe": "string",
      "time_min": 0,
      "ingredients_used": ["string"],
      "missing_required_for_target": ["string"],
      "missing_optional": ["string"],
      "steps": ["string"],
      "anti_waste_tip": "string",
      "allergen_alerts": ["string"],
      "nutrition_notes": ["string"],
      "shopping_list": ["string"],
      "policy_status": "unchecked"
    }}
  ],
  "global_explanation": "string",
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
    recipe_response.recognized_ingredients = readiness.recognized_items
    recipe_response.can_generate_recipes = bool(recipe_response.recipes)

    recipe_response, availability_warnings = remove_invalid_recipes(recipe_response, readiness.usable_ingredients)
    if availability_warnings and not recipe_response.recipes:
        fallback = build_no_recipe_response(readiness)
        fallback.safety_notes.extend(availability_warnings)
        return fallback

    recipe_response = mark_policy_status(recipe_response, profile)
    violations = validate_recipe_response(recipe_response, profile)
    if violations:
        recipe_response.safety_notes.extend(["Revisión local: " + violation for violation in violations])

    if not recipe_response.recipes:
        return build_no_recipe_response(readiness)

    return recipe_response
