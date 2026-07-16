from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from src.fridgechef.availability import normalize_text, unique_clean
from src.fridgechef.name_matching import inventory_name_key
from src.fridgechef.models import (
    BarcodeObservation,
    FridgeAnalysis,
    IngredientMention,
    InventoryItem,
    InventoryQuantityChange,
    InventoryUpdateResult,
)
from src.fridgechef.quantities import (
    display_quantity_label,
    format_quantity_parts,
    merge_quantity_parts,
    normalize_quantity_parts,
    parse_quantity_label,
)


def _source_label(source: str) -> str:
    """Translate internal source names into friendly labels without lookup tables."""
    if source == "manual":
        return "Escrito manualmente"
    if source == "upload":
        return "Foto subida"
    if source == "device_camera":
        return "Foto del dispositivo"
    if source == "internal_camera":
        return "Cámara interna"
    if source == "session":
        return "Nevera guardada"
    return source


def _merge_sources(existing: Iterable[str], new: Iterable[str]) -> list[str]:
    """Merge source labels without duplicates."""
    return unique_clean([*existing, *new])


def _expiry_for_name(name: str, observations: list[BarcodeObservation]) -> str | None:
    """Attach a visible expiry date when the vision model can relate it to a product."""
    name_key = normalize_text(name)
    for observation in observations:
        if not observation.expiry_text:
            continue
        guess = normalize_text(observation.product_name_guess or "")
        if not guess or guess in name_key or name_key in guess:
            return observation.expiry_text
    return None


def item_to_recipe_name(item: InventoryItem) -> str:
    """Return the clean ingredient name used by the recipe generator."""
    return item.name


def inventory_to_recipe_ingredients(inventory: Iterable[InventoryItem]) -> list[str]:
    """Convert the current inventory into a recipe input list without duplicates."""
    return unique_clean(
        item_to_recipe_name(item)
        for item in inventory
        if item.name and item.state not in {"possible_spoiled", "spoiled"}
    )


def _quantity_fields(label: object) -> dict[str, object]:
    """Create backward-compatible quantity fields from a model or user label."""
    parts = parse_quantity_label(label)
    unit_count = parts.get("unit", 1.0)
    return {
        "quantity": max(1, int(round(unit_count))),
        "quantity_parts": parts,
        "quantity_label": format_quantity_parts(parts, "es"),
    }


def _manual_inventory(
    manual_ingredients: list[str],
    manual_items: list[IngredientMention] | None,
) -> list[InventoryItem]:
    """Build and sum explicit manual mentions before combining other inputs."""
    items: list[InventoryItem] = []
    now_note = f"Actualizado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    mentions = manual_items or [
        IngredientMention(name=ingredient, quantity_label="Cantidad no indicada", confidence=1.0)
        for ingredient in manual_ingredients
    ]

    for mention in mentions:
        name = mention.name.strip()
        key = inventory_name_key(name)
        if not key:
            continue
        notes = [*mention.notes, now_note]
        if mention.source_text:
            notes.insert(0, f"Texto original: {mention.source_text}")
        items.append(
            InventoryItem(
                name=name,
                normalized_name=key,
                state=mention.state or "unknown",
                confidence=mention.confidence or 1.0,
                sources=[_source_label("manual")],
                notes=unique_clean(notes),
                **_quantity_fields(mention.quantity_label),
            )
        )

    return consolidate_inventory(items, quantity_mode="sum")


def _image_inventory(analysis: FridgeAnalysis | None, source: str) -> list[InventoryItem]:
    """Build one image inventory while deduplicating repeated model detections."""
    if analysis is None:
        return []

    items: list[InventoryItem] = []
    now_note = f"Actualizado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    source_label = _source_label(source)
    spoiled_keys = {inventory_name_key(item.name) for item in analysis.possible_spoiled_items}

    for ingredient in analysis.visible_ingredients:
        name = ingredient.name.strip()
        key = inventory_name_key(name)
        if not key:
            continue

        state = ingredient.state or "unknown"
        if key in spoiled_keys:
            state = "possible_spoiled"

        items.append(
            InventoryItem(
                name=name,
                normalized_name=key,
                state=state,
                expiry_text=_expiry_for_name(name, analysis.barcode_observations),
                confidence=ingredient.confidence,
                sources=[source_label],
                notes=[note for note in [ingredient.evidence, now_note] if note],
                **_quantity_fields(ingredient.quantity_estimate or "Cantidad no indicada"),
            )
        )

    return consolidate_inventory(items, quantity_mode="max")


def inventory_from_inputs(
    manual_ingredients: list[str],
    analysis: FridgeAnalysis | None,
    source: str = "manual",
    manual_items: list[IngredientMention] | None = None,
) -> list[InventoryItem]:
    """Build inventory from one manual input and one optional image source."""
    groups: list[list[InventoryItem]] = []
    manual_group = _manual_inventory(manual_ingredients, manual_items)
    if manual_group:
        groups.append(manual_group)
    image_group = _image_inventory(analysis, source)
    if image_group:
        groups.append(image_group)
    return combine_input_inventories(groups)


def _choose_better_name(existing: InventoryItem, incoming: InventoryItem) -> str:
    """Prefer the most informative display name for repeated inventory items."""
    if len(incoming.name) > len(existing.name) and incoming.confidence >= existing.confidence:
        return incoming.name
    return existing.name


def _merged_state(existing: InventoryItem, incoming: InventoryItem) -> str:
    """Preserve the most cautious freshness state across matching observations."""
    better_state = incoming.state if existing.state in {"unknown", "fresh"} else existing.state
    if incoming.state in {"aging", "possible_spoiled", "spoiled"}:
        better_state = incoming.state
    return better_state


def _merge_item(existing: InventoryItem, incoming: InventoryItem, *, quantity_mode: str) -> InventoryItem:
    """Merge item metadata while using an explicit quantity policy."""
    existing_parts = normalize_quantity_parts(existing.quantity_parts, existing.quantity_label)
    incoming_parts = normalize_quantity_parts(incoming.quantity_parts, incoming.quantity_label)
    parts = merge_quantity_parts(existing_parts, incoming_parts, mode=quantity_mode)
    unit_count = parts.get("unit", max(existing.quantity, incoming.quantity, 1))

    return InventoryItem(
        name=_choose_better_name(existing, incoming),
        normalized_name=existing.normalized_name,
        quantity=max(1, int(round(unit_count))),
        quantity_label=format_quantity_parts(parts, "es"),
        quantity_parts=parts,
        state=_merged_state(existing, incoming),
        expiry_text=incoming.expiry_text or existing.expiry_text,
        confidence=max(existing.confidence, incoming.confidence),
        sources=_merge_sources(existing.sources, incoming.sources),
        notes=unique_clean([*existing.notes, *incoming.notes]),
    )


def consolidate_inventory(
    items: Iterable[InventoryItem],
    *,
    quantity_mode: str = "max",
) -> list[InventoryItem]:
    """Deduplicate one source while preserving or summing quantities as requested."""
    consolidated: dict[str, InventoryItem] = {}
    for raw_item in items:
        key = inventory_name_key(raw_item.name or raw_item.normalized_name)
        if not key:
            continue

        parts = normalize_quantity_parts(raw_item.quantity_parts, raw_item.quantity_label)
        item = raw_item.model_copy(
            update={
                "normalized_name": key,
                "quantity_parts": parts,
                "quantity_label": format_quantity_parts(parts, "es"),
                "quantity": max(1, int(round(parts.get("unit", raw_item.quantity or 1)))),
            }
        )
        if key in consolidated:
            consolidated[key] = _merge_item(
                consolidated[key],
                item,
                quantity_mode=quantity_mode,
            )
        else:
            consolidated[key] = item

    return sorted(consolidated.values(), key=lambda value: value.name.lower())


def combine_input_inventories(
    inventories: Iterable[Iterable[InventoryItem]],
) -> list[InventoryItem]:
    """Sum the same food across distinct manual, upload, device and internal inputs."""
    combined: dict[str, InventoryItem] = {}
    for inventory in inventories:
        for item in consolidate_inventory(inventory, quantity_mode="max"):
            key = inventory_name_key(item.name or item.normalized_name)
            if key in combined:
                combined[key] = _merge_item(combined[key], item, quantity_mode="sum")
            else:
                combined[key] = item

    return sorted(combined.values(), key=lambda value: value.name.lower())


def apply_inventory_update(
    existing_inventory: list[InventoryItem],
    incoming_items: list[InventoryItem],
    mode: str,
) -> InventoryUpdateResult:
    """Apply replacement or additive semantics without clearing on an empty analysis."""
    mode = "add" if mode == "add" else "replace"
    existing = consolidate_inventory(existing_inventory, quantity_mode="max")
    incoming = consolidate_inventory(incoming_items, quantity_mode="max")
    existing_by_key = {item.normalized_name: item for item in existing}
    incoming_by_key = {item.normalized_name: item for item in incoming}

    # An empty result is never a command to erase the saved fridge. This guard is
    # deliberately kept at the domain layer as well as the UI layer.
    if not incoming_by_key:
        return InventoryUpdateResult(inventory=existing, mode=mode)

    if mode == "replace":
        removed = [item.name for key, item in existing_by_key.items() if key not in incoming_by_key]
        added = [item.name for key, item in incoming_by_key.items() if key not in existing_by_key]
        updated = [item.name for key, item in incoming_by_key.items() if key in existing_by_key]
        return InventoryUpdateResult(
            inventory=list(incoming_by_key.values()),
            added=added,
            updated=updated,
            removed=removed,
            mode=mode,
        )

    merged = dict(existing_by_key)
    added: list[str] = []
    updated: list[str] = []
    quantity_changes: list[InventoryQuantityChange] = []

    for key, incoming_item in incoming_by_key.items():
        if key in merged:
            existing_item = merged[key]
            merged_item = _merge_item(existing_item, incoming_item, quantity_mode="sum")
            merged[key] = merged_item
            updated.append(merged_item.name)
            quantity_changes.append(
                InventoryQuantityChange(
                    name=merged_item.name,
                    previous_quantity_label=display_quantity_label(
                        existing_item.quantity_parts,
                        existing_item.quantity_label,
                        "es",
                    ),
                    incoming_quantity_label=display_quantity_label(
                        incoming_item.quantity_parts,
                        incoming_item.quantity_label,
                        "es",
                    ),
                    resulting_quantity_label=display_quantity_label(
                        merged_item.quantity_parts,
                        merged_item.quantity_label,
                        "es",
                    ),
                )
            )
        else:
            merged[key] = incoming_item
            added.append(incoming_item.name)

    return InventoryUpdateResult(
        inventory=consolidate_inventory(merged.values(), quantity_mode="max"),
        added=added,
        updated=updated,
        removed=[],
        quantity_changes=quantity_changes,
        mode=mode,
    )


def needs_replace_confirmation(
    existing_inventory: list[InventoryItem],
    incoming_items: list[InventoryItem],
    mode: str,
) -> bool:
    """Avoid accidental deletion when the new input is much smaller than the saved inventory."""
    if mode != "replace" or not existing_inventory or not incoming_items:
        return False
    existing_count = len({item.normalized_name for item in existing_inventory})
    incoming_count = len({item.normalized_name for item in incoming_items})
    return existing_count >= 4 and incoming_count < max(2, existing_count // 2)


def friendly_state_label(state: str) -> str:
    """Return a display label for visual freshness states without lookup tables."""
    if state == "fresh":
        return "Parece en buen estado"
    if state == "aging":
        return "Conviene usarlo pronto"
    if state == "possible_spoiled":
        return "Revisar antes de usar"
    if state == "spoiled":
        return "No usar sin revisar"
    return "Estado no confirmado"
