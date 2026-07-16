from __future__ import annotations

from pathlib import Path

from scripts.patch_utils import replace_once


APP_PATH = Path("streamlit_app/app.py")


def apply_patch() -> None:
    """Avoid rendering detected-food feedback below recipe generation results."""
    text = APP_PATH.read_text(encoding="utf-8")
    old = (
        "        if result:\n"
        "            parse_result, update_result, response = result\n"
        "            show_manual_feedback(parse_result)\n"
        "            if update_result and remember_fridge:\n"
        "                show_inventory_update(update_result)\n"
        "            show_recipes(response, profile, show_images=generate_recipe_images)\n"
    )
    new = (
        "        if result:\n"
        "            _, _, response = result\n"
        "            show_recipes(response, profile, show_images=generate_recipe_images)\n"
    )
    if new in text:
        print("Recipe-only result rendering is already applied.")
        return
    text = replace_once(text, old, new, "recipe result rendering")
    APP_PATH.write_text(text, encoding="utf-8")
    print("Applied recipe-only result rendering.")


if __name__ == "__main__":
    apply_patch()
