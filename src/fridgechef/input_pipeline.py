from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.fridgechef.inventory import combine_input_inventories, inventory_from_inputs
from src.fridgechef.models import FridgeAnalysis, IngredientMention, InventoryItem


@dataclass(frozen=True)
class PreparedImageInput:
    """One independently prepared image that participates in the next action."""

    source: str
    image_bytes: bytes
    mime_type: str
    caption: str


def build_incoming_inventory(
    manual_items: list[IngredientMention],
    image_analyses: Iterable[tuple[str, FridgeAnalysis]],
) -> list[InventoryItem]:
    """Combine manual text and every prepared image using additive input semantics."""
    groups: list[list[InventoryItem]] = []
    if manual_items:
        groups.append(inventory_from_inputs([], None, manual_items=manual_items))
    for source, analysis in image_analyses:
        group = inventory_from_inputs([], analysis, source=source)
        if group:
            groups.append(group)
    return combine_input_inventories(groups)


def merge_fridge_analyses(analyses: Iterable[FridgeAnalysis]) -> FridgeAnalysis | None:
    """Create one session-friendly analysis from all successful image calls."""
    values = list(analyses)
    if not values:
        return None
    return FridgeAnalysis(
        visible_ingredients=[item for analysis in values for item in analysis.visible_ingredients],
        possible_spoiled_items=[item for analysis in values for item in analysis.possible_spoiled_items],
        uncertain_items=[item for analysis in values for item in analysis.uncertain_items],
        barcode_observations=[item for analysis in values for item in analysis.barcode_observations],
        notes=[item for analysis in values for item in analysis.notes],
    )
