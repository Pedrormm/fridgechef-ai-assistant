from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_saved_inventory_expander_has_no_streamlit_runtime_exception() -> None:
    """Run the responsive saved-inventory structure through Streamlit itself."""
    app = AppTest.from_string(
        """
import streamlit as st

inventory = [
    {"name": "Patatas", "quantity": "3 unidades", "state": "En buen estado"},
    {"name": "Tomates", "quantity": "2 unidades", "state": "Revisar pronto"},
]
key_scope = "saved_inventory_top_editable"
with st.expander(
    "Alimentos guardados",
    expanded=False,
    key=f"{key_scope}_expander",
    width="stretch",
):
    columns = st.columns(2)
    for index, item in enumerate(inventory):
        with columns[index % 2]:
            with st.container(border=True):
                st.markdown(f"#### {item['name']}")
                st.button("Editar", key=f"edit_{index}")
                st.button("Eliminar", key=f"delete_{index}")
                st.write(f"Cantidad: {item['quantity']}")
                st.write(f"Estado: {item['state']}")
        """,
        default_timeout=10,
    ).run()

    assert not app.exception
