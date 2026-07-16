from __future__ import annotations

from pathlib import Path

from scripts.patch_utils import replace_once


APP_PATH = Path("streamlit_app/app.py")


def apply_patch() -> None:
    """Show structured quantities and friendly additive update explanations."""
    text = APP_PATH.read_text(encoding="utf-8")
    if "for change in update_result.quantity_changes" in text:
        print("Additive quantity UI is already applied.")
        return

    text = replace_once(
        text,
        '        updated_item = item.model_copy(\n            update={\n                "name": validation.name,\n                "normalized_name": validation.normalized_name,\n                "quantity_label": validation.quantity_label,\n                "state": validation.state,\n            }\n        )\n',
        '        quantity_parts = parse_quantity_label(validation.quantity_label)\n'
        '        updated_item = item.model_copy(\n'
        '            update={\n'
        '                "name": validation.name,\n'
        '                "normalized_name": validation.normalized_name,\n'
        '                "quantity": max(1, int(round(quantity_parts.get("unit", 1.0)))),\n'
        '                "quantity_label": format_quantity_parts(quantity_parts, "es"),\n'
        '                "quantity_parts": quantity_parts,\n'
        '                "state": validation.state,\n'
        '            }\n'
        '        )\n',
        "inventory edit quantity normalization",
    )
    text = replace_once(
        text,
        '            f"{sentence_case(item.name)} ({clean_user_text(item.quantity_label)})"\n            if item.quantity_label != "Cantidad no indicada"\n            else sentence_case(item.name)\n',
        '            f"{sentence_case(item.name)} "\n'
        '            f"({display_quantity_label({}, item.quantity_label, current_language())})"\n',
        "manual feedback quantity display",
    )
    text = replace_once(
        text,
        '                st.write(f"**Cantidad:** {clean_user_text(item.quantity_label)}")\n',
        '                quantity_text = display_quantity_label(\n'
        '                    item.quantity_parts,\n'
        '                    item.quantity_label,\n'
        '                    current_language(),\n'
        '                )\n'
        '                st.write(f"**Cantidad:** {clean_user_text(quantity_text)}")\n',
        "inventory card quantity display",
    )
    text = replace_once(
        text,
        '        message = _html_text("He añadido los alimentos nuevos sin duplicar los que ya estaban guardados.")\n',
        '        message = _html_text(\n'
        '            "He añadido los alimentos nuevos y he sumado las cantidades cuando ya estaban guardados."\n'
        '        )\n',
        "additive update summary",
    )
    text = replace_once(
        text,
        '    if details:\n        st.caption(" · ".join(details))\n',
        '    if details:\n'
        '        st.caption(" · ".join(details))\n'
        '\n'
        '    for change in update_result.quantity_changes:\n'
        '        if current_language() == "en":\n'
        '            quantity_message = (\n'
        '                f"{sentence_case(change.name)}: there were "\n'
        '                f"{display_quantity_label({}, change.previous_quantity_label, \'en\')}, "\n'
        '                f"{display_quantity_label({}, change.incoming_quantity_label, \'en\')} were added, "\n'
        '                f"and there are now "\n'
        '                f"{display_quantity_label({}, change.resulting_quantity_label, \'en\')}."\n'
        '            )\n'
        '        else:\n'
        '            quantity_message = (\n'
        '                f"{sentence_case(change.name)}: había "\n'
        '                f"{display_quantity_label({}, change.previous_quantity_label, \'es\')}, "\n'
        '                f"se han añadido "\n'
        '                f"{display_quantity_label({}, change.incoming_quantity_label, \'es\')} "\n'
        '                f"y ahora hay "\n'
        '                f"{display_quantity_label({}, change.resulting_quantity_label, \'es\')}."\n'
        '            )\n'
        '        st.info(quantity_message, __skip_i18n=True)\n',
        "friendly quantity change details",
    )

    APP_PATH.write_text(text, encoding="utf-8")
    print("Applied additive quantity display and messages.")


if __name__ == "__main__":
    apply_patch()
