from __future__ import annotations

from types import SimpleNamespace

from src.fridgechef.food_name_normalizer import (
    FoodNameBatch,
    FoodNameDecision,
    normalize_food_names,
    sanitize_action_inputs,
    sanitize_inventory_items,
    sanitize_recipe_response,
    strip_commercial_terms,
)
from src.fridgechef.models import (
    BarcodeObservation,
    DetectedIngredient,
    FridgeAnalysis,
    IngredientMention,
    InventoryItem,
    RecipeItem,
    RecipeResponse,
)
from src.fridgechef.text_parser import ManualIngredientParseResult


def _temporary_settings(tmp_path):
    return SimpleNamespace(
        local_database_path=str(tmp_path / "fridgechef-test.db"),
        model_name="test-model",
        text_fallback_models="",
    )


def test_local_guard_removes_known_brands_and_keeps_culinary_details():
    assert strip_commercial_terms("Bacon en tiras ahumado natural Realvalle") == "Bacon en tiras ahumado natural"
    assert strip_commercial_terms("Filetes finos de lomo de cerdo Duroc El Pozo") == "Filetes finos de lomo de cerdo"
    assert strip_commercial_terms("Yogur griego Alipende (sabor miel y nueces)") == "Yogur griego (sabor miel y nueces)"
    assert strip_commercial_terms("Filetes de pechuga extrafinos de pollo Alipende") == "Filetes de pechuga extrafinos de pollo"
    assert strip_commercial_terms("Piña o maíz troceado") == "Piña o maíz troceado"


def test_agent_guard_rejects_an_invented_replacement(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.fridgechef.food_name_normalizer.get_settings",
        lambda: _temporary_settings(tmp_path),
    )

    def agent(names):
        return FoodNameBatch(
            items=[
                FoodNameDecision(
                    original_name=names[0],
                    cleaned_name="Salmón ahumado",
                    is_food=True,
                    removed_commercial_terms=["Realvalle"],
                    confidence=0.99,
                )
            ]
        )

    result = normalize_food_names(
        ["Bacon en tiras ahumado natural Realvalle"],
        agent=agent,
        use_cache=False,
    )

    assert result.decisions[0].cleaned_name == "Bacon en tiras ahumado natural"


def test_action_callback_cleans_manual_and_visual_names(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.fridgechef.food_name_normalizer.get_settings",
        lambda: _temporary_settings(tmp_path),
    )

    parse_result = ManualIngredientParseResult(
        accepted=["Yogur griego Alipende (sabor miel y nueces)"],
        accepted_items=[
            IngredientMention(
                name="Yogur griego Alipende (sabor miel y nueces)",
                source_text="Yogur griego Alipende (sabor miel y nueces)",
                confidence=0.95,
            )
        ],
        used_agent=True,
    )
    analysis = FridgeAnalysis(
        visible_ingredients=[
            DetectedIngredient(
                name="Filetes finos de lomo de cerdo Duroc El Pozo",
                quantity_estimate="1 unidad",
                state="fresh",
                confidence=0.91,
                evidence="Envase El Pozo sellado.",
            )
        ],
        barcode_observations=[
            BarcodeObservation(
                product_name_guess="Filetes finos de lomo de cerdo Duroc El Pozo",
                expiry_text="17.07.26",
            )
        ],
    )

    def agent(names):
        decisions = []
        for name in names:
            if "Yogur" in name:
                cleaned = "Yogur griego (sabor miel y nueces)"
                removed = ["Alipende"]
            else:
                cleaned = "Filetes finos de lomo de cerdo"
                removed = ["Duroc", "El Pozo"]
            decisions.append(
                FoodNameDecision(
                    original_name=name,
                    cleaned_name=cleaned,
                    is_food=True,
                    removed_commercial_terms=removed,
                    confidence=0.98,
                )
            )
        return FoodNameBatch(items=decisions)

    cleaned_parse, cleaned_images, _ = sanitize_action_inputs(
        parse_result,
        [("upload", analysis)],
        agent=agent,
    )

    assert cleaned_parse.accepted == ["Yogur griego (sabor miel y nueces)"]
    assert cleaned_parse.accepted_items[0].source_text == ""
    cleaned_analysis = cleaned_images[0][1]
    assert cleaned_analysis.visible_ingredients[0].name == "Filetes finos de lomo de cerdo"
    assert cleaned_analysis.visible_ingredients[0].evidence == "Envase sellado"
    assert cleaned_analysis.barcode_observations[0].product_name_guess == "Filetes finos de lomo de cerdo"


def test_inventory_migration_preserves_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.fridgechef.food_name_normalizer.get_settings",
        lambda: _temporary_settings(tmp_path),
    )
    original = InventoryItem(
        name="Bacon en tiras ahumado natural Realvalle",
        normalized_name="bacon en tiras ahumado natural realvalle",
        quantity=2,
        quantity_label="2 unidades",
        quantity_parts={"unit": 2.0},
        state="fresh",
        expiry_text="18.07.26",
        confidence=0.94,
        sources=["Foto subida"],
        notes=["Envase Realvalle sellado."],
    )

    def agent(names):
        return FoodNameBatch(
            items=[
                FoodNameDecision(
                    original_name=names[0],
                    cleaned_name="Bacon en tiras ahumado natural",
                    is_food=True,
                    removed_commercial_terms=["Realvalle"],
                    confidence=0.99,
                )
            ]
        )

    cleaned, _ = sanitize_inventory_items([original], agent=agent)
    item = cleaned[0]
    assert item.name == "Bacon en tiras ahumado natural"
    assert item.quantity == 2
    assert item.state == "fresh"
    assert item.expiry_text == "18.07.26"
    assert item.sources == ["Foto subida"]
    assert item.notes == ["Envase sellado"]


def test_recipe_output_callback_removes_commercial_terms(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.fridgechef.food_name_normalizer.get_settings",
        lambda: _temporary_settings(tmp_path),
    )
    response = RecipeResponse(
        recipes=[
            RecipeItem(
                title="Salteado de bacon Realvalle y pollo Alipende",
                description="Receta con productos Alipende.",
                why_this_recipe="Aprovecha el bacon Realvalle.",
                time_min=20,
                ingredients_used=["Bacon Realvalle", "Pollo Alipende"],
                steps=["Cocina el bacon Realvalle."],
                anti_waste_tip="Guarda el pollo Alipende restante.",
            )
        ],
        global_explanation="Receta preparada con Alipende.",
    )

    cleaned = sanitize_recipe_response(response)
    recipe = cleaned.recipes[0]
    assert recipe.title == "Salteado de bacon y pollo"
    assert recipe.ingredients_used == ["Bacon", "Pollo"]
    assert all("Alipende" not in value and "Realvalle" not in value for value in [
        recipe.description,
        recipe.why_this_recipe,
        recipe.steps[0],
        recipe.anti_waste_tip,
        cleaned.global_explanation,
    ])
