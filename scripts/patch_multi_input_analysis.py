from __future__ import annotations

from pathlib import Path

from scripts.patch_utils import replace_regex_once


APP_PATH = Path("streamlit_app/app.py")


def apply_patch() -> None:
    """Analyze all prepared inputs before applying one safe inventory update."""
    text = APP_PATH.read_text(encoding="utf-8")
    if '"input_sources": [' in text and "prepared_images: list[PreparedImageInput]" in text:
        print("Multi-input analysis is already applied.")
        return

    replacement = '''def analyze_current_inputs(
    manual_text: str,
    profile: UserProfile,
    remember_fridge: bool,
    update_mode: UpdateMode,
    confirm_replace: bool,
    prepared_images: list[PreparedImageInput] | None = None,
    no_food_message: str | None = None,
) -> ActionResult:
    """Analyze every prepared input before applying one atomic inventory update."""
    validate_profile_preferences(profile)
    parse_result = parse_manual_ingredients(manual_text)
    images = list(prepared_images or [])

    if not manual_text.strip() and not images:
        if remember_fridge and get_inventory():
            return None, None, parse_result
        raise UserFacingError(
            no_food_message
            or "No hay texto ni fotos preparados. Escribe algún alimento o añade una foto para empezar."
        )

    if manual_text.strip() and not parse_result.accepted_items and not images:
        if not parse_result.used_agent:
            raise UserFacingError(
                "No he podido conectar con el agente de IA que entiende los alimentos. "
                "El texto parece válido, pero ahora mismo no puedo revisarlo con Gemini."
            )
        raise UserFacingError(
            "No he encontrado alimentos claros en el texto. "
            "Escribe alimentos concretos, con cantidades si las conoces, y vuelve a intentarlo."
        )

    image_results: list[tuple[str, FridgeAnalysis]] = []
    for prepared_image in images:
        validate_image_upload(
            prepared_image.image_bytes,
            prepared_image.mime_type,
            settings.max_image_mb,
        )
        try:
            image_analysis = analyze_image_bytes(
                prepared_image.image_bytes,
                prepared_image.mime_type,
            )
        except ImageValidationError:
            raise
        except Exception as exc:
            raise UserFacingError(
                f"No he podido analizar {prepared_image.caption.lower()}. "
                "No he cambiado la nevera guardada. Vuelve a intentarlo en unos segundos."
            ) from exc
        image_results.append((prepared_image.source, image_analysis))

    incoming_items = build_incoming_inventory(
        parse_result.accepted_items,
        image_results,
    )
    if not incoming_items:
        if manual_text.strip() and images:
            message = (
                "No he encontrado alimentos ni en el texto ni en las fotos preparadas. "
                "Mantengo la nevera guardada tal como estaba."
            )
        elif images:
            message = (
                "No he encontrado alimentos claros en las fotos preparadas. "
                "Mantengo la nevera guardada tal como estaba."
            )
        elif not parse_result.used_agent:
            message = (
                "No he podido conectar con el agente de IA que entiende los alimentos. "
                "No he cambiado la nevera guardada."
            )
        else:
            message = (
                "No he encontrado alimentos claros en el texto. "
                "Mantengo la nevera guardada tal como estaba."
            )
        raise UserFacingError(message)

    analysis = merge_fridge_analyses(result for _, result in image_results)
    update_result = None
    if remember_fridge:
        existing_inventory = get_inventory()
        if needs_replace_confirmation(existing_inventory, incoming_items, update_mode) and not confirm_replace:
            raise UserFacingError(
                "Parece que esta entrada tiene muchos menos alimentos que tu nevera guardada. "
                "Si es una entrada parcial, elige 'Añadir sin borrar lo anterior'. "
                "Si realmente quieres sustituirlo todo, marca la confirmación."
            )
        update_result = apply_inventory_update(existing_inventory, incoming_items, update_mode)
        set_inventory(update_result.inventory, persist=True)
        st.session_state["clear_consumed_inputs"] = True
        session_id = save_session_if_allowed(
            {
                "event": "inventory_update",
                "update_mode": update_mode,
                "input_sources": [
                    *(("manual",) if parse_result.accepted_items else ()),
                    *(source for source, _ in image_results),
                ],
                "fridge_inventory": [item.model_dump() for item in update_result.inventory],
            },
            allow_save=True,
        )
        if session_id:
            st.session_state["last_inventory_session_id"] = session_id
    else:
        update_result = InventoryUpdateResult(
            inventory=incoming_items,
            added=[item.name for item in incoming_items],
            mode="replace",
        )

    st.session_state["last_analysis"] = analysis.model_dump() if analysis else None
    st.session_state["last_update"] = update_result.model_dump() if update_result else None
    return analysis, update_result, parse_result


def generate_recipes_from_current_inventory('''
    text = replace_regex_once(
        text,
        r"def analyze_current_inputs\(.*?\n\n\ndef generate_recipes_from_current_inventory\(",
        replacement,
        "multi-input analysis function",
    )

    APP_PATH.write_text(text, encoding="utf-8")
    print("Applied atomic analysis of every prepared input.")


if __name__ == "__main__":
    apply_patch()
