from src.fridgechef.models import RecipeItem, RecipeResponse, RecipeReadinessAssessment, UserProfile
from src.fridgechef.recipe_planner import clean_user_text, generate_recipes, post_process_recipe_response
from src.fridgechef.availability import IngredientReadiness


def test_recipe_generation_uses_safe_fallback_when_model_fails(monkeypatch):
    import src.fridgechef.availability as availability
    import src.fridgechef.recipe_planner as recipe_planner

    def ready_agent(manual_ingredients, image_analysis):
        return RecipeReadinessAssessment(
            can_generate=True,
            usable_ingredients=manual_ingredients,
            recognized_items=manual_ingredients,
            no_recipe_reason="",
        )

    monkeypatch.setattr(availability, "_run_recipe_readiness_agent", ready_agent)
    monkeypatch.setattr(recipe_planner, "get_client", lambda: (_ for _ in ()).throw(RuntimeError("offline")))

    response = generate_recipes(["pimientos", "pollo", "huevos de codorniz"], UserProfile(), None)

    assert response.can_generate_recipes
    assert response.recipes
    used = {ingredient.lower() for ingredient in response.recipes[0].ingredients_used}
    assert used.issubset({"pimientos", "pollo", "huevos de codorniz"})


def test_recipe_count_is_limited_by_available_ingredients(monkeypatch):
    import src.fridgechef.availability as availability
    import src.fridgechef.recipe_planner as recipe_planner

    def ready_agent(manual_ingredients, image_analysis):
        return RecipeReadinessAssessment(
            can_generate=True,
            usable_ingredients=manual_ingredients,
            recognized_items=manual_ingredients,
            no_recipe_reason="",
        )

    monkeypatch.setattr(availability, "_run_recipe_readiness_agent", ready_agent)
    monkeypatch.setattr(recipe_planner, "get_client", lambda: (_ for _ in ()).throw(RuntimeError("offline")))

    response = generate_recipes(["pimientos", "pollo", "tomates cherry"], UserProfile(recipe_count=5), None)

    assert len(response.recipes) == 2
    assert "5" in response.global_explanation
    assert "2" in response.global_explanation


def test_recipe_post_processing_removes_html_fragments():
    response = RecipeResponse(
        recipes=[
            RecipeItem(
                title="<b>plato de prueba</b>",
                description="<div>descripción útil</div>",
                why_this_recipe="<span>encaja bien</span>",
                time_min=30,
                ingredients_used=["<b>pimientos</b>"],
                steps=["<div>corta los pimientos</div>"],
                anti_waste_tip="<span>guarda las sobras</span>",
            )
        ],
        global_explanation="<div>explicación</div>",
    )
    readiness = IngredientReadiness(
        can_generate=True,
        usable_ingredients=["pimientos"],
        recognized_items=["pimientos"],
        reason="ok",
    )

    cleaned = post_process_recipe_response(response, readiness, UserProfile())

    assert "<" not in cleaned.recipes[0].title
    assert "<" not in cleaned.recipes[0].description
    assert "<" not in cleaned.recipes[0].steps[0]
    assert clean_user_text("<div>hola</div>") == "hola"
