from __future__ import annotations

from pathlib import Path

from scripts.patch_utils import replace_once


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "streamlit_app" / "app.py"
WORKFLOW = ROOT / ".github" / "workflows" / "apply-additive-multi-input.yml"


OLD_INVENTORY_RENDERER = '''def show_inventory(
    inventory: list[InventoryItem],
    title: str = "Alimentos guardados",
    editable: bool = False,
    widget_namespace: str | None = None,
) -> None:
    """Display inventory cards with widget keys scoped to this rendered section."""
    st.subheader(title)
    if not inventory:
        st.info("Todavía no hay alimentos guardados. Escribe ingredientes o sube una foto para empezar.")
        return

    key_scope = _selector_key(widget_namespace or f"{title}_{'editable' if editable else 'readonly'}")
    columns = st.columns(2)
    for index, item in enumerate(inventory):
        with columns[index % 2]:
            with st.container(border=True):
                item_key = item.normalized_name or item.name
                base_key = _inventory_item_key(item, index)
                if editable:
                    title_col, edit_col, delete_col = st.columns([0.74, 0.13, 0.13])
                    with title_col:
                        st.markdown(f"#### {sentence_case(item.name)}")
                    with edit_col:
                        if st.button("✏️", key=inventory_action_key(key_scope, "edit", base_key, index), help="Editar alimento", width="stretch"):
                            show_edit_inventory_dialog(item_key)
                    with delete_col:
                        if st.button("🗑️", key=inventory_action_key(key_scope, "delete", base_key, index), help="Eliminar alimento", width="stretch"):
                            show_delete_inventory_dialog(item_key)
                else:
                    st.markdown(f"#### {sentence_case(item.name)}")

                quantity_text = display_quantity_label(
                    item.quantity_parts,
                    item.quantity_label,
                    current_language(),
                )
                st.write(f"**Cantidad:** {clean_user_text(quantity_text)}")
                st.write(f"**Estado:** {friendly_state_label(item.state)}")
                if item.expiry_text:
                    st.write(f"**Caducidad visible:** {clean_user_text(item.expiry_text)}")
                if item.sources:
                    st.caption("Origen: " + ", ".join(clean_user_text(source) for source in item.sources))
                public_notes = [clean_user_text(note) for note in item.notes[:2] if clean_user_text(note)]
                for note in public_notes:
                    st.caption(note)
'''

NEW_INVENTORY_RENDERER = '''def _render_inventory_cards(
    inventory: list[InventoryItem],
    *,
    editable: bool,
    key_scope: str,
) -> None:
    """Render inventory cards inside the section container selected by the caller."""
    columns = st.columns(2)
    for index, item in enumerate(inventory):
        with columns[index % 2]:
            with st.container(border=True):
                item_key = item.normalized_name or item.name
                base_key = _inventory_item_key(item, index)
                if editable:
                    title_col, edit_col, delete_col = st.columns([0.74, 0.13, 0.13])
                    with title_col:
                        st.markdown(f"#### {sentence_case(item.name)}")
                    with edit_col:
                        if st.button("✏️", key=inventory_action_key(key_scope, "edit", base_key, index), help="Editar alimento", width="stretch"):
                            show_edit_inventory_dialog(item_key)
                    with delete_col:
                        if st.button("🗑️", key=inventory_action_key(key_scope, "delete", base_key, index), help="Eliminar alimento", width="stretch"):
                            show_delete_inventory_dialog(item_key)
                else:
                    st.markdown(f"#### {sentence_case(item.name)}")

                quantity_text = display_quantity_label(
                    item.quantity_parts,
                    item.quantity_label,
                    current_language(),
                )
                st.write(f"**Cantidad:** {clean_user_text(quantity_text)}")
                st.write(f"**Estado:** {friendly_state_label(item.state)}")
                if item.expiry_text:
                    st.write(f"**Caducidad visible:** {clean_user_text(item.expiry_text)}")
                if item.sources:
                    st.caption("Origen: " + ", ".join(clean_user_text(source) for source in item.sources))
                public_notes = [clean_user_text(note) for note in item.notes[:2] if clean_user_text(note)]
                for note in public_notes:
                    st.caption(note)


def show_inventory(
    inventory: list[InventoryItem],
    title: str = "Alimentos guardados",
    editable: bool = False,
    widget_namespace: str | None = None,
    collapsible: bool = False,
    initially_expanded: bool = False,
) -> None:
    """Display an inventory section while preserving scoped edit and delete keys."""
    if not inventory:
        # Keep the empty-state explanation visible because there are no cards to hide.
        st.subheader(title)
        st.info("Todavía no hay alimentos guardados. Escribe ingredientes o sube una foto para empezar.")
        return

    key_scope = _selector_key(widget_namespace or f"{title}_{'editable' if editable else 'readonly'}")
    if collapsible:
        # One outer expander controls the complete saved inventory. The cards stay
        # in a single container, so desktop and mobile users can open or close the
        # whole section without nesting additional expanders inside item cards.
        with st.expander(title, expanded=initially_expanded):
            _render_inventory_cards(inventory, editable=editable, key_scope=key_scope)
        return

    st.subheader(title)
    _render_inventory_cards(inventory, editable=editable, key_scope=key_scope)
'''

OLD_TOP_CALL = '''    show_inventory(
        get_inventory(),
        title="Alimentos guardados",
        editable=True,
        widget_namespace="saved_inventory_top",
    )
'''

NEW_TOP_CALL = '''    show_inventory(
        get_inventory(),
        title="Alimentos guardados",
        editable=True,
        widget_namespace="saved_inventory_top",
        collapsible=True,
        initially_expanded=False,
    )
'''

OLD_WORKFLOW_STEP = '''      - name: Verify brand-free food normalization
        run: python -m scripts.patch_brand_free_food_names
'''

NEW_WORKFLOW_STEP = '''      - name: Verify brand-free food normalization
        run: python -m scripts.patch_brand_free_food_names

      - name: Verify collapsed saved inventory section
        run: python -m scripts.patch_saved_inventory_expander
'''


def _replace(source: str, old: str, new: str, description: str) -> str:
    """Apply one exact migration and make repeated CI verification idempotent."""
    if new in source:
        return source
    return replace_once(source, old, new, description)


def apply() -> None:
    """Materialize the saved-inventory expander and its permanent CI guard."""
    app_source = APP.read_text(encoding="utf-8")
    app_source = _replace(
        app_source,
        OLD_INVENTORY_RENDERER,
        NEW_INVENTORY_RENDERER,
        "saved inventory renderer",
    )
    app_source = _replace(
        app_source,
        OLD_TOP_CALL,
        NEW_TOP_CALL,
        "top saved inventory call",
    )
    APP.write_text(app_source, encoding="utf-8")

    workflow_source = WORKFLOW.read_text(encoding="utf-8")
    workflow_source = _replace(
        workflow_source,
        OLD_WORKFLOW_STEP,
        NEW_WORKFLOW_STEP,
        "saved inventory CI verification step",
    )
    WORKFLOW.write_text(workflow_source, encoding="utf-8")


if __name__ == "__main__":
    apply()
