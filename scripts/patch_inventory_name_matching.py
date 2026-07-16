from __future__ import annotations

from pathlib import Path

from scripts.patch_utils import replace_once


INVENTORY_PATH = Path("src/fridgechef/inventory.py")


def apply_patch() -> None:
    """Use canonical food-name keys without changing the displayed item name."""
    text = INVENTORY_PATH.read_text(encoding="utf-8")
    if "from src.fridgechef.name_matching import inventory_name_key" in text:
        print("Canonical inventory name matching is already applied.")
        return

    text = replace_once(
        text,
        "from src.fridgechef.availability import normalize_text, unique_clean\n",
        "from src.fridgechef.availability import normalize_text, unique_clean\n"
        "from src.fridgechef.name_matching import inventory_name_key\n",
        "inventory name matching import",
    )
    assignment = "        key = normalize_text(name)\n"
    if text.count(assignment) != 2:
        raise RuntimeError("Expected two complete input-name key assignments.")
    text = text.replace(assignment, "        key = inventory_name_key(name)\n")
    text = replace_once(
        text,
        "spoiled_keys = {normalize_text(item.name) for item in analysis.possible_spoiled_items}",
        "spoiled_keys = {inventory_name_key(item.name) for item in analysis.possible_spoiled_items}",
        "spoiled image key set",
    )
    text = replace_once(
        text,
        "key = raw_item.normalized_name or normalize_text(raw_item.name)",
        "key = inventory_name_key(raw_item.name or raw_item.normalized_name)",
        "consolidation key",
    )
    text = replace_once(
        text,
        "key = item.normalized_name or normalize_text(item.name)",
        "key = inventory_name_key(item.name or item.normalized_name)",
        "combined input key",
    )

    INVENTORY_PATH.write_text(text, encoding="utf-8")
    print("Applied singular and plural inventory name matching.")


if __name__ == "__main__":
    apply_patch()
