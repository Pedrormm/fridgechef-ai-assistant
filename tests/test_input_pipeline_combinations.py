from itertools import combinations

from src.fridgechef.input_pipeline import build_incoming_inventory
from src.fridgechef.models import DetectedIngredient, FridgeAnalysis, IngredientMention


CHANNELS = ("manual", "upload", "device_camera", "internal_camera")


def _image_analysis() -> FridgeAnalysis:
    return FridgeAnalysis(
        visible_ingredients=[DetectedIngredient(name="naranjas", quantity_estimate="1 unidad")]
    )


def test_every_non_empty_input_combination_is_processed_together():
    for size in range(1, len(CHANNELS) + 1):
        for selected in combinations(CHANNELS, size):
            manual_items = (
                [IngredientMention(name="naranjas", quantity_label="1 unidad", confidence=1.0)]
                if "manual" in selected
                else []
            )
            image_analyses = [
                (source, _image_analysis())
                for source in selected
                if source != "manual"
            ]

            incoming = build_incoming_inventory(manual_items, image_analyses)

            assert len(incoming) == 1
            assert incoming[0].quantity_label == f"{len(selected)} " + (
                "unidad" if len(selected) == 1 else "unidades"
            )


def test_distinct_foods_from_different_channels_remain_separate():
    manual_items = [IngredientMention(name="patatas", quantity_label="2 unidades", confidence=1.0)]
    upload = FridgeAnalysis(
        visible_ingredients=[DetectedIngredient(name="naranjas", quantity_estimate="3 unidades")]
    )
    internal = FridgeAnalysis(
        visible_ingredients=[DetectedIngredient(name="leche", quantity_estimate="1 litro")]
    )

    incoming = build_incoming_inventory(
        manual_items,
        [("upload", upload), ("internal_camera", internal)],
    )

    assert {item.normalized_name for item in incoming} == {"patata", "naranja", "leche"}
