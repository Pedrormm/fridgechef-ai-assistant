from __future__ import annotations

from pathlib import Path

from scripts.patch_utils import replace_once


APP_PATH = Path("streamlit_app/app.py")


def apply_patch() -> None:
    """Keep empty-input messages accurate and quantity updates natural in English."""
    text = APP_PATH.read_text(encoding="utf-8")
    marker = "the fridge had {previous_quantity}"
    if marker in text:
        print("Multi-input messages are already polished.")
        return

    text = replace_once(
        text,
        '    if not incoming_items:\n'
        '        if manual_text.strip() and images:\n'
        '            message = (\n'
        '                "No he encontrado alimentos ni en el texto ni en las fotos preparadas. "\n'
        '                "Mantengo la nevera guardada tal como estaba."\n'
        '            )\n'
        '        elif images:\n'
        '            message = (\n'
        '                "No he encontrado alimentos claros en las fotos preparadas. "\n'
        '                "Mantengo la nevera guardada tal como estaba."\n'
        '            )\n'
        '        elif not parse_result.used_agent:\n'
        '            message = (\n'
        '                "No he podido conectar con el agente de IA que entiende los alimentos. "\n'
        '                "No he cambiado la nevera guardada."\n'
        '            )\n'
        '        else:\n'
        '            message = (\n'
        '                "No he encontrado alimentos claros en el texto. "\n'
        '                "Mantengo la nevera guardada tal como estaba."\n'
        '            )\n'
        '        raise UserFacingError(message)\n',
        '    if not incoming_items:\n'
        '        unchanged_message = (\n'
        '            "Mantengo la nevera guardada tal como estaba."\n'
        '            if remember_fridge and get_inventory()\n'
        '            else "No se ha guardado ningún cambio."\n'
        '        )\n'
        '        if manual_text.strip() and images:\n'
        '            message = (\n'
        '                "No he encontrado alimentos ni en el texto ni en las fotos preparadas. "\n'
        '                + unchanged_message\n'
        '            )\n'
        '        elif images:\n'
        '            message = (\n'
        '                "No he encontrado alimentos claros en las fotos preparadas. "\n'
        '                + unchanged_message\n'
        '            )\n'
        '        elif not parse_result.used_agent:\n'
        '            message = (\n'
        '                "No he podido conectar con el agente de IA que entiende los alimentos. "\n'
        '                + unchanged_message\n'
        '            )\n'
        '        else:\n'
        '            message = "No he encontrado alimentos claros en el texto. " + unchanged_message\n'
        '        raise UserFacingError(message)\n',
        "empty analyzed input message",
    )
    text = replace_once(
        text,
        '        if current_language() == "en":\n'
        '            quantity_message = (\n'
        '                f"{sentence_case(change.name)}: there were "\n'
        '                f"{display_quantity_label({}, change.previous_quantity_label, \'en\')}, "\n'
        '                f"{display_quantity_label({}, change.incoming_quantity_label, \'en\')} were added, "\n'
        '                f"and there are now "\n'
        '                f"{display_quantity_label({}, change.resulting_quantity_label, \'en\')}."\n'
        '            )\n',
        '        if current_language() == "en":\n'
        '            previous_quantity = display_quantity_label(\n'
        '                {}, change.previous_quantity_label, "en"\n'
        '            )\n'
        '            incoming_quantity = display_quantity_label(\n'
        '                {}, change.incoming_quantity_label, "en"\n'
        '            )\n'
        '            resulting_quantity = display_quantity_label(\n'
        '                {}, change.resulting_quantity_label, "en"\n'
        '            )\n'
        '            quantity_message = (\n'
        '                f"{sentence_case(change.name)}: the fridge had {previous_quantity}; "\n'
        '                f"I added {incoming_quantity}, so it now has {resulting_quantity}."\n'
        '            )\n',
        "English additive quantity message",
    )

    APP_PATH.write_text(text, encoding="utf-8")
    print("Polished multi-input result messages.")


if __name__ == "__main__":
    apply_patch()
