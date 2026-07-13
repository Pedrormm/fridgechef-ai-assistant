from src.fridgechef.models import RecipeItem, RecipeResponse, UserProfile
from src.fridgechef.policy import blocked_terms_for_profile, validate_recipe_response


def _recipe(*ingredients: str) -> RecipeResponse:
    return RecipeResponse(
        recipes=[
            RecipeItem(
                title="Receta de prueba",
                description="x",
                why_this_recipe="x",
                time_min=10,
                ingredients_used=list(ingredients),
                steps=["x"],
                anti_waste_tip="x",
            )
        ],
        global_explanation="x",
    )


def test_policy_uses_explicit_user_restrictions_without_static_food_lists():
    profile = UserProfile(allergies=["frutos secos"])
    response = _recipe("Frutos secos")
    assert validate_recipe_response(response, profile)


def test_policy_agent_can_apply_semantic_diet_rules():
    profile = UserProfile(diet=["Vegana"])
    response = _recipe("ingrediente no compatible")

    def agent(recipe, profile):
        return ["La receta no encaja con la dieta indicada."]

    assert validate_recipe_response(response, profile, policy_agent=agent)


def test_blocked_terms_are_only_values_provided_by_the_user():
    profile = UserProfile(diet=["Vegana"], allergies=["sésamo"], dislikes=["cilantro"])
    blocked = blocked_terms_for_profile(profile)
    assert "sesamo" in blocked
    assert "cilantro" in blocked
    assert "vegana" not in blocked
