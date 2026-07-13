from src.fridgechef.availability import assess_recipe_readiness, build_no_recipe_response
from src.fridgechef.models import DetectedIngredient, FridgeAnalysis, IgnoredTextFragment, RecipeReadinessAssessment


def test_water_bottles_do_not_trigger_recipe_generation_with_readiness_agent():
    analysis = FridgeAnalysis(
        visible_ingredients=[DetectedIngredient(name="botellas de agua", confidence=0.95, state="unknown")]
    )

    def readiness_agent(manual_ingredients, image_analysis):
        return RecipeReadinessAssessment(
            can_generate=False,
            usable_ingredients=[],
            recognized_items=["botellas de agua"],
            no_recipe_reason="He reconocido botellas de agua, pero no hay alimentos suficientes para cocinar.",
            ignored_items=[IgnoredTextFragment(text="botellas de agua", reason="No basta para generar recetas.")],
        )

    readiness = assess_recipe_readiness([], analysis, readiness_agent=readiness_agent)
    assert not readiness.can_generate
    assert readiness.recognized_items == ["botellas de agua"]
    assert readiness.used_agent


def test_real_manual_ingredient_can_trigger_recipe_generation_with_readiness_agent():
    def readiness_agent(manual_ingredients, image_analysis):
        return RecipeReadinessAssessment(
            can_generate=True,
            usable_ingredients=["huevos"],
            recognized_items=["huevos"],
            no_recipe_reason="",
        )

    readiness = assess_recipe_readiness(["huevos"], None, readiness_agent=readiness_agent)
    assert readiness.can_generate
    assert readiness.usable_ingredients == ["huevos"]


def test_no_recipe_response_is_friendly_and_empty():
    analysis = FridgeAnalysis(
        visible_ingredients=[DetectedIngredient(name="agua", confidence=0.95, state="unknown")]
    )

    def readiness_agent(manual_ingredients, image_analysis):
        return RecipeReadinessAssessment(
            can_generate=False,
            usable_ingredients=[],
            recognized_items=["agua"],
            no_recipe_reason="He reconocido agua, pero no hay ingredientes suficientes para preparar recetas.",
        )

    readiness = assess_recipe_readiness([], analysis, readiness_agent=readiness_agent)
    response = build_no_recipe_response(readiness)
    assert not response.can_generate_recipes
    assert response.recipes == []
    assert "ingredientes suficientes" in response.global_explanation.lower()


def test_image_only_fallback_does_not_generate_without_readiness_agent(monkeypatch):
    analysis = FridgeAnalysis(
        visible_ingredients=[DetectedIngredient(name="botellas de agua", confidence=0.95, state="unknown")]
    )

    import src.fridgechef.availability as availability

    def broken_agent(manual_ingredients, image_analysis):
        raise RuntimeError("agent unavailable")

    readiness = availability.assess_recipe_readiness([], analysis, readiness_agent=broken_agent)
    assert not readiness.can_generate
    assert readiness.recognized_items == ["botellas de agua"]
