from src.fridgechef.models import UserProfile, RecipeItem, RecipeResponse
from src.fridgechef.policy import validate_recipe_response


def test_vegan_blocks_cheese_and_egg():
    profile = UserProfile(diet=["vegana"])
    response = RecipeResponse(
        recipes=[RecipeItem(title="Tortilla", description="x", why_this_recipe="x", time_min=10, ingredients_used=["huevo", "queso"], steps=["x"], anti_waste_tip="x")],
        global_explanation="x",
    )
    warnings = validate_recipe_response(response, profile)
    assert warnings


def test_lactose_blocks_milk():
    profile = UserProfile(intolerances=["lactosa"])
    response = RecipeResponse(
        recipes=[RecipeItem(title="Crema", description="x", why_this_recipe="x", time_min=10, ingredients_used=["leche"], steps=["x"], anti_waste_tip="x")],
        global_explanation="x",
    )
    assert validate_recipe_response(response, profile)
