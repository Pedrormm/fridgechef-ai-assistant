from __future__ import annotations

from pathlib import Path

from scripts.patch_utils import replace_once


APP_PATH = Path("streamlit_app/app.py")


def apply_patch() -> None:
    """Replace saved food only after successful detection, without extra confirmation."""
    text = APP_PATH.read_text(encoding="utf-8")
    if "needs_replace_confirmation" not in text and "st.caption(clean_user_text(exc))" not in text:
        print("Safe replace semantics are already applied.")
        return

    text = text.replace("    needs_replace_confirmation,\n", "", 1)
    text = replace_once(
        text,
        '        if needs_replace_confirmation(existing_inventory, incoming_items, update_mode) and not confirm_replace:\n'
        '            raise UserFacingError(\n'
        '                "Parece que esta entrada tiene muchos menos alimentos que tu nevera guardada. "\n'
        '                "Si es una entrada parcial, elige \'Añadir sin borrar lo anterior\'. "\n'
        '                "Si realmente quieres sustituirlo todo, marca la confirmación."\n'
        '            )\n',
        "",
        "replace confirmation guard",
    )
    text = replace_once(
        text,
        'confirm_replace = False\n'
        'if remember_fridge and update_mode == "replace" and get_inventory():\n'
        '    confirm_replace = st.checkbox(\n'
        '        "Confirmo que esta entrada representa la nevera completa y sustituye lo que había anteriormente",\n'
        '        value=False,\n'
        '        help="Solo es necesario marcarlo cuando la nueva entrada parece mucho más pequeña que el inventario guardado.",\n'
        '    )\n',
        "confirm_replace = False\n",
        "replace confirmation widget",
    )
    text = text.replace("            st.caption(clean_user_text(exc))\n", "", 1)

    APP_PATH.write_text(text, encoding="utf-8")
    print("Applied detection-first replace semantics and friendly camera errors.")


if __name__ == "__main__":
    apply_patch()
