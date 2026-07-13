from src.fridgechef.inventory import apply_inventory_update, inventory_from_inputs, inventory_to_recipe_ingredients
from src.fridgechef.models import DetectedIngredient, FridgeAnalysis, InventoryItem


def test_add_mode_merges_existing_items_without_duplicates():
    existing = [
        InventoryItem(name="Tomate", normalized_name="tomate", quantity_label="2 unidades", sources=["Foto subida"])
    ]
    incoming = [
        InventoryItem(name="tomate", normalized_name="tomate", quantity_label="Cantidad no indicada", sources=["Cámara interna"]),
        InventoryItem(name="Lechuga", normalized_name="lechuga", sources=["Cámara interna"]),
    ]

    result = apply_inventory_update(existing, incoming, mode="add")

    assert len(result.inventory) == 2
    assert sorted(item.normalized_name for item in result.inventory) == ["lechuga", "tomate"]
    tomato = next(item for item in result.inventory if item.normalized_name == "tomate")
    assert "Foto subida" in tomato.sources
    assert "Cámara interna" in tomato.sources


def test_replace_mode_removes_items_not_seen_anymore():
    existing = [
        InventoryItem(name="Tomate", normalized_name="tomate"),
        InventoryItem(name="Lechuga", normalized_name="lechuga"),
    ]
    incoming = [InventoryItem(name="Arroz", normalized_name="arroz")]

    result = apply_inventory_update(existing, incoming, mode="replace")

    assert [item.normalized_name for item in result.inventory] == ["arroz"]
    assert sorted(result.removed) == ["Lechuga", "Tomate"]


def test_inventory_from_image_deduplicates_repeated_detected_food():
    analysis = FridgeAnalysis(
        visible_ingredients=[
            DetectedIngredient(name="tomate", quantity_estimate="2 unidades", confidence=0.9),
            DetectedIngredient(name="Tomate", quantity_estimate="2 unidades", confidence=0.8),
        ]
    )

    items = inventory_from_inputs([], analysis, source="upload")

    assert len(items) == 1
    assert items[0].normalized_name == "tomate"


def test_spoiled_items_are_not_used_for_recipes():
    inventory = [
        InventoryItem(name="Tomate", normalized_name="tomate", state="possible_spoiled"),
        InventoryItem(name="Arroz", normalized_name="arroz", state="fresh"),
    ]

    assert inventory_to_recipe_ingredients(inventory) == ["Arroz"]
