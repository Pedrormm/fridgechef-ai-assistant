from src.fridgechef.availability import assess_recipe_readiness, build_no_recipe_response
from src.fridgechef.models import DetectedIngredient, FridgeAnalysis


def test_water_bottles_do_not_trigger_recipe_generation():
    analysis = FridgeAnalysis(
        visible_ingredients=[DetectedIngredient(name="botellas de agua", confidence=0.95, state="unknown")]
    )
    readiness = assess_recipe_readiness([], analysis)
    assert not readiness.can_generate
    assert readiness.recognized_items == ["botellas de agua"]


def test_real_manual_ingredient_can_trigger_recipe_generation():
    readiness = assess_recipe_readiness(["huevos"], None)
    assert readiness.can_generate
    assert readiness.usable_ingredients == ["huevos"]


def test_no_recipe_response_is_friendly_and_empty():
    analysis = FridgeAnalysis(
        visible_ingredients=[DetectedIngredient(name="agua", confidence=0.95, state="unknown")]
    )
    readiness = assess_recipe_readiness([], analysis)
    response = build_no_recipe_response(readiness)
    assert not response.can_generate_recipes
    assert response.recipes == []
    assert "no puedo" in response.global_explanation.lower()
