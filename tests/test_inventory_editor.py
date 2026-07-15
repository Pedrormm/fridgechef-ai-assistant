from src.fridgechef.inventory_editor import (
    build_delete_confirmation_text,
    inventory_state_options,
    inventory_state_select_label,
    validate_inventory_edit,
)


def test_inventory_edit_accepts_only_safe_state_values_quickly():
    result = validate_inventory_edit("Zanahoria", "2 unidades", "possible_spoiled")

    assert result.ok is True
    assert result.name == "Zanahoria"
    assert result.quantity_label == "2 unidades"
    assert result.state == "possible_spoiled"


def test_inventory_state_select_labels_are_polished_in_both_languages():
    states = inventory_state_options()

    assert states == ("fresh", "aging", "possible_spoiled", "spoiled", "unknown")
    assert [inventory_state_select_label(state, "en") for state in states] == [
        "Fresh",
        "Aging",
        "Possible spoiled",
        "Spoiled",
        "Unknown",
    ]
    assert [inventory_state_select_label(state, "es") for state in states] == [
        "Fresco",
        "Envejeciendo",
        "Posiblemente estropeado",
        "Estropeado",
        "Desconocido",
    ]


def test_inventory_edit_rejects_problematic_local_fields():
    result = validate_inventory_edit("", "2 unidades", "fresh")

    assert result.ok is False
    assert "Escribe el nombre" in result.messages_es[0]


def test_delete_confirmation_keeps_friendly_article():
    assert build_delete_confirmation_text("zanahoria", "es") == "¿Quieres eliminar la zanahoria de la nevera?"
    assert build_delete_confirmation_text("huevos", "es") == "¿Quieres eliminar los huevos de la nevera?"
    assert build_delete_confirmation_text("tuna", "en") == "Do you want to remove tuna from your fridge?"
