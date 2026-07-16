"""Regression tests for inventory widget key isolation."""

from src.fridgechef.ui_keys import inventory_action_key


def test_inventory_keys_are_scoped_by_rendered_section():
    top_key = inventory_action_key("saved_inventory_top", "edit", "carne picada de cerdo", 0)
    result_key = inventory_action_key(
        "saved_inventory_analysis_result",
        "edit",
        "carne picada de cerdo",
        0,
    )

    assert top_key != result_key
    assert top_key == "saved_inventory_top_edit_inventory_0_carne_picada_de_cerdo"
    assert result_key == "saved_inventory_analysis_result_edit_inventory_0_carne_picada_de_cerdo"


def test_inventory_edit_and_delete_keys_are_different():
    edit_key = inventory_action_key("saved_inventory_top", "edit", "tomate", 0)
    delete_key = inventory_action_key("saved_inventory_top", "delete", "tomate", 0)

    assert edit_key != delete_key
