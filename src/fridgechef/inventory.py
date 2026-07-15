from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from src.fridgechef.availability import normalize_text, unique_clean
from src.fridgechef.models import BarcodeObservation, FridgeAnalysis, IngredientMention, InventoryItem, InventoryUpdateResult


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


def inventory_from_inputs(
    manual_ingredients: list[str],
    analysis: FridgeAnalysis | None,
    source: str = "manual",
    manual_items: list[IngredientMention] | None = None,
) -> list[InventoryItem]:
    """Build normalized inventory items from manual text and optional image analysis."""
    items: list[InventoryItem] = []
    now_note = f"Actualizado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"

    manual_mentions = manual_items or [
        IngredientMention(name=ingredient, quantity_label="Añadido manualmente", confidence=1.0)
        for ingredient in manual_ingredients
    ]

    for mention in manual_mentions:
        name = mention.name.strip()
        key = normalize_text(name)
        if not key:
            continue
        notes = [*mention.notes, now_note]
        if mention.source_text:
            notes.insert(0, f"Texto original: {mention.source_text}")
        items.append(
            InventoryItem(
                name=name,
                normalized_name=key,
                quantity=1,
                quantity_label=mention.quantity_label or "Cantidad no indicada",
                state=mention.state or "unknown",
                confidence=mention.confidence or 1.0,
                sources=[_source_label("manual")],
                notes=unique_clean(notes),
            )
        )

    if analysis:
        source_label = _source_label(source)
        spoiled_keys = {normalize_text(item.name) for item in analysis.possible_spoiled_items}
        for ingredient in analysis.visible_ingredients:
            name = ingredient.name.strip()
            key = normalize_text(name)
            if not key:
                continue

            state = ingredient.state or "unknown"
            if key in spoiled_keys:
                state = "possible_spoiled"

            items.append(
                InventoryItem(
                    name=name,
                    normalized_name=key,
                    quantity=1,
                    quantity_label=ingredient.quantity_estimate or "Cantidad no indicada",
                    state=state,
                    expiry_text=_expiry_for_name(name, analysis.barcode_observations),
                    confidence=ingredient.confidence,
                    sources=[source_label],
                    notes=[note for note in [ingredient.evidence, now_note] if note],
                )
            )

    return consolidate_inventory(items)


def _choose_better_name(existing: InventoryItem, incoming: InventoryItem) -> str:
    """Prefer the most informative display name for repeated inventory items."""
    if len(incoming.name) > len(existing.name) and incoming.confidence >= existing.confidence:
        return incoming.name
    return existing.name


def _merge_item(existing: InventoryItem, incoming: InventoryItem) -> InventoryItem:
    """Merge repeated detections without counting the same food multiple times."""
    better_state = incoming.state if existing.state in {"unknown", "fresh"} else existing.state
    if incoming.state in {"aging", "possible_spoiled", "spoiled"}:
        better_state = incoming.state

    return InventoryItem(
        name=_choose_better_name(existing, incoming),
        normalized_name=existing.normalized_name,
        quantity=max(existing.quantity, incoming.quantity),
        quantity_label=incoming.quantity_label if incoming.quantity_label != "Cantidad no indicada" else existing.quantity_label,
        state=better_state,
        expiry_text=incoming.expiry_text or existing.expiry_text,
        confidence=max(existing.confidence, incoming.confidence),
        sources=_merge_sources(existing.sources, incoming.sources),
        notes=unique_clean([*existing.notes, *incoming.notes]),
    )


def consolidate_inventory(items: Iterable[InventoryItem]) -> list[InventoryItem]:
    """Deduplicate inventory items by normalized name while preserving useful metadata."""
    consolidated: dict[str, InventoryItem] = {}
    for item in items:
        key = item.normalized_name or normalize_text(item.name)
        if not key:
            continue
        if key in consolidated:
            consolidated[key] = _merge_item(consolidated[key], item)
        else:
            consolidated[key] = item.model_copy(update={"normalized_name": key})
    return sorted(consolidated.values(), key=lambda value: value.name.lower())


def apply_inventory_update(
    existing_inventory: list[InventoryItem],
    incoming_items: list[InventoryItem],
    mode: str,
) -> InventoryUpdateResult:
    """Apply either a full replacement or a safe additive update to the inventory."""
    mode = "add" if mode == "add" else "replace"
    existing_by_key = {item.normalized_name: item for item in existing_inventory}
    incoming_by_key = {item.normalized_name: item for item in consolidate_inventory(incoming_items)}

    if mode == "replace":
        inventory = list(incoming_by_key.values())
        removed = [item.name for key, item in existing_by_key.items() if key not in incoming_by_key]
        added = [item.name for key, item in incoming_by_key.items() if key not in existing_by_key]
        updated = [item.name for key, item in incoming_by_key.items() if key in existing_by_key]
        return InventoryUpdateResult(inventory=inventory, added=added, updated=updated, removed=removed, mode=mode)

    merged = dict(existing_by_key)
    added: list[str] = []
    updated: list[str] = []

    for key, incoming in incoming_by_key.items():
        if key in merged:
            merged[key] = _merge_item(merged[key], incoming)
            updated.append(merged[key].name)
        else:
            merged[key] = incoming
            added.append(incoming.name)

    return InventoryUpdateResult(
        inventory=consolidate_inventory(merged.values()),
        added=added,
        updated=updated,
        removed=[],
        mode=mode,
    )


def needs_replace_confirmation(existing_inventory: list[InventoryItem], incoming_items: list[InventoryItem], mode: str) -> bool:
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
