from __future__ import annotations

import inspect

import streamlit as st


def test_saved_inventory_expander_runtime_api_supports_stable_keys() -> None:
    """Pin the Streamlit API required by the responsive saved-inventory section."""
    parameters = inspect.signature(st.expander).parameters

    assert "expanded" in parameters
    assert "key" in parameters
    assert "width" in parameters
    assert parameters["width"].default == "stretch"
