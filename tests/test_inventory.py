from src.fridgechef.input_pipeline import build_incoming_inventory
from src.fridgechef.inventory import apply_inventory_update, inventory_from_inputs, inventory_to_recipe_ingredients
from src.fridgechef.models import DetectedIngredient, FridgeAnalysis, IngredientMention, InventoryItem


def test_add_mode_sums_existing_countable_items():
    existing = [InventoryItem(name="Patatas", normalized_name="patatas", quantity_label="3 unidades")]
    incoming = [InventoryItem(name="patatas", normalized_name="patatas", quantity_label="2 unidades")]

    result = apply_inventory_update(existing, incoming, mode="add")

    assert len(result.inventory) == 1
    assert result.inventory[0].quantity_label == "5 unidades"
    assert result.quantity_changes[0].previous_quantity_label == "3 unidades"
    assert result.quantity_changes[0].incoming_quantity_label == "2 unidades"
    assert result.quantity_changes[0].resulting_quantity_label == "5 unidades"


def test_add_mode_treats_an_unspecified_saved_quantity_as_one_unit():
    existing = [InventoryItem(name="Patatas", normalized_name="patatas", quantity_label="Cantidad no indicada")]
    incoming = [InventoryItem(name="patatas", normalized_name="patatas", quantity_label="2 unidades")]

    result = apply_inventory_update(existing, incoming, mode="add")

    assert result.inventory[0].quantity_label == "3 unidades"


def test_add_mode_merges_sources_without_duplicates():
    existing = [
        InventoryItem(name="Tomate", normalized_name="tomate", quantity_label="2 unidades", sources=["Foto subida"])
    ]
    incoming = [
        InventoryItem(name="tomate", normalized_name="tomate", quantity_label="1 unidad", sources=["Cámara interna"]),
        InventoryItem(name="Lechuga", normalized_name="lechuga", sources=["Cámara interna"]),
    ]

    result = apply_inventory_update(existing, incoming, mode="add")

    assert len(result.inventory) == 2
    tomato = next(item for item in result.inventory if item.normalized_name == "tomate")
    assert tomato.quantity_label == "3 unidades"
    assert "Foto subida" in tomato.sources
    assert "Cámara interna" in tomato.sources


def test_replace_mode_keeps_only_the_new_quantities():
    existing = [InventoryItem(name="Naranjas", normalized_name="naranjas", quantity_label="5 unidades")]
    incoming = [InventoryItem(name="naranjas", normalized_name="naranjas", quantity_label="3 unidades")]

    result = apply_inventory_update(existing, incoming, mode="replace")

    assert result.inventory[0].quantity_label == "3 unidades"
    assert result.quantity_changes == []


def test_replace_mode_removes_items_not_seen_anymore():
    existing = [
        InventoryItem(name="Tomate", normalized_name="tomate"),
        InventoryItem(name="Lechuga", normalized_name="lechuga"),
    ]
    incoming = [InventoryItem(name="Arroz", normalized_name="arroz")]

    result = apply_inventory_update(existing, incoming, mode="replace")

    assert [item.normalized_name for item in result.inventory] == ["arroz"]
    assert sorted(result.removed) == ["Lechuga", "Tomate"]


def test_empty_replace_never_clears_the_saved_inventory():
    existing = [InventoryItem(name="Tomate", normalized_name="tomate", quantity_label="2 unidades")]

    result = apply_inventory_update(existing, [], mode="replace")

    assert len(result.inventory) == 1
    assert result.inventory[0].normalized_name == "tomate"


def test_repeated_detection_inside_one_image_uses_the_largest_estimate_once():
    analysis = FridgeAnalysis(
        visible_ingredients=[
            DetectedIngredient(name="tomate", quantity_estimate="2 unidades", confidence=0.9),
            DetectedIngredient(name="Tomate", quantity_estimate="2 unidades", confidence=0.8),
        ]
    )

    items = inventory_from_inputs([], analysis, source="upload")

    assert len(items) == 1
    assert items[0].normalized_name == "tomate"
    assert items[0].quantity_label == "2 unidades"


def test_all_four_input_channels_are_combined_before_inventory_update():
    manual = [IngredientMention(name="naranjas", quantity_label="2 unidades", confidence=1.0)]
    upload = FridgeAnalysis(
        visible_ingredients=[DetectedIngredient(name="naranjas", quantity_estimate="3 unidades")]
    )
    device = FridgeAnalysis(
        visible_ingredients=[DetectedIngredient(name="naranjas", quantity_estimate="1 unidad")]
    )
    internal = FridgeAnalysis(
        visible_ingredients=[DetectedIngredient(name="naranjas", quantity_estimate="2 unidades")]
    )

    incoming = build_incoming_inventory(
        manual,
        [("upload", upload), ("device_camera", device), ("internal_camera", internal)],
    )

    assert len(incoming) == 1
    assert incoming[0].quantity_label == "8 unidades"
    assert sorted(incoming[0].sources) == [
        "Cámara interna",
        "Escrito manualmente",
        "Foto del dispositivo",
        "Foto subida",
    ]


def test_image_quantity_is_added_to_saved_quantity():
    existing = [InventoryItem(name="Naranjas", normalized_name="naranjas", quantity_label="5 unidades")]
    analysis = FridgeAnalysis(
        visible_ingredients=[DetectedIngredient(name="naranjas", quantity_estimate="3 unidades")]
    )
    incoming = build_incoming_inventory([], [("upload", analysis)])

    result = apply_inventory_update(existing, incoming, mode="add")

    assert result.inventory[0].quantity_label == "8 unidades"


def test_spoiled_items_are_not_used_for_recipes():
    inventory = [
        InventoryItem(name="Tomate", normalized_name="tomate", state="possible_spoiled"),
        InventoryItem(name="Arroz", normalized_name="arroz", state="fresh"),
    ]

    assert inventory_to_recipe_ingredients(inventory) == ["Arroz"]


def test_manual_spoiled_state_is_preserved_in_inventory():
    items = inventory_from_inputs(
        [],
        None,
        manual_items=[
            IngredientMention(
                name="tomates",
                quantity_label="5 unidades",
                state="spoiled",
                source_text="5 tomates podridos",
                confidence=0.99,
            )
        ],
    )

    assert len(items) == 1
    assert items[0].name == "tomates"
    assert items[0].quantity_label == "5 unidades"
    assert items[0].state == "spoiled"
    assert inventory_to_recipe_ingredients(items) == []
