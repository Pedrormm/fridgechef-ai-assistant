from __future__ import annotations

import re
from dataclasses import dataclass

from src.fridgechef.availability import normalize_text


@dataclass(frozen=True)
class FieldValidationResult:
    """Fast, local validation result for one editable inventory field."""

    ok: bool
    value: str
    reason_es: str = ""
    reason_en: str = ""


@dataclass(frozen=True)
class InventoryEditValidation:
    """Combined validation result for the ingredient edit modal."""

    ok: bool
    name: str
    normalized_name: str
    quantity_label: str
    state: str
    messages_es: tuple[str, ...] = ()
    messages_en: tuple[str, ...] = ()


def _clean_text(value: object) -> str:
    """Normalize whitespace in a user-editable field without changing the meaning."""
    return re.sub(r"\s+", " ", str(value or "").strip())


def _has_unsafe_text(value: str) -> bool:
    """Reject characters that are not useful in a fridge inventory card."""
    return bool(re.search(r"[<>\\{}\[\]|`~]", value or ""))


def _has_letters(value: str) -> bool:
    """Check that a field contains human-readable text."""
    return bool(re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", value or ""))


def inventory_state_options() -> tuple[str, str, str, str, str]:
    """Return the safe internal states accepted by the edit dialog."""
    return ("fresh", "aging", "possible_spoiled", "spoiled", "unknown")


def is_valid_inventory_state(value: object) -> bool:
    """Keep saved items inside the small set of states understood by the app."""
    return str(value or "").strip() in inventory_state_options()


def inventory_state_select_label(state: object, language: str = "es") -> str:
    """Return a polished label for one internal state without external calls."""
    clean_state = str(state or "unknown").strip()
    selected_language = str(language or "es").lower()

    if selected_language.startswith("en"):
        if clean_state == "fresh":
            return "Fresh"
        if clean_state == "aging":
            return "Aging"
        if clean_state == "possible_spoiled":
            return "Possible spoiled"
        if clean_state == "spoiled":
            return "Spoiled"
        return "Unknown"

    if clean_state == "fresh":
        return "Fresco"
    if clean_state == "aging":
        return "Envejeciendo"
    if clean_state == "possible_spoiled":
        return "Posiblemente estropeado"
    if clean_state == "spoiled":
        return "Estropeado"
    return "Desconocido"


def _validate_name(value: object) -> FieldValidationResult:
    """Validate the ingredient name locally so saving the modal is immediate."""
    clean = _clean_text(value)
    if not clean:
        return FieldValidationResult(False, "", "Escribe el nombre del alimento.", "Enter the food name.")
    if len(clean) > 70 or _has_unsafe_text(clean) or not _has_letters(clean):
        return FieldValidationResult(
            False,
            clean,
            "El nombre del alimento debe ser breve y claro.",
            "The food name should be short and clear.",
        )
    return FieldValidationResult(True, clean)


def _validate_quantity(value: object) -> FieldValidationResult:
    """Validate a free-text quantity without calling an external model."""
    clean = _clean_text(value)
    if not clean:
        clean = "Cantidad no indicada"
    if len(clean) > 80 or _has_unsafe_text(clean):
        return FieldValidationResult(
            False,
            clean,
            "La cantidad debe ser breve, por ejemplo '2 unidades', '500 gramos' o 'Cantidad no indicada'.",
            "The quantity should be short, for example '2 units', '500 grams', or 'Quantity not specified'.",
        )
    return FieldValidationResult(True, clean)


def _state_from_text(value: str) -> str:
    """Map natural Spanish or English status text to the app's stable internal states."""
    lowered = normalize_text(value)
    if not lowered:
        return "unknown"
    if re.search(r"\b(no|sin)\b.*\b(confirm|indic|saber)\b", lowered) or "unknown" in lowered or "unconfirmed" in lowered:
        return "unknown"
    if "fresc" in lowered or "fresh" in lowered or "buen estado" in lowered or "good" in lowered:
        return "fresh"
    if "pronto" in lowered or "use soon" in lowered or "aging" in lowered or "madur" in lowered:
        return "aging"
    if "revis" in lowered or "duda" in lowered or "doubt" in lowered or "possible" in lowered:
        return "possible_spoiled"
    if "podrid" in lowered or "malo" in lowered or "bad" in lowered or "spoiled" in lowered or "caduc" in lowered:
        return "spoiled"
    return "unknown"


def _validate_state(value: object) -> FieldValidationResult:
    """Validate the selected freshness/status immediately and deterministically."""
    clean = _clean_text(value)
    if is_valid_inventory_state(clean):
        return FieldValidationResult(True, clean)

    # Keep old saved values and manually typed legacy text usable, but never save
    # an unknown free-form status. The modal now sends internal states from a
    # selectbox, so this branch is only a safety net for older sessions/tests.
    normalized_state = _state_from_text(clean)
    if is_valid_inventory_state(normalized_state):
        return FieldValidationResult(True, normalized_state)

    return FieldValidationResult(
        False,
        clean,
        "Elige uno de los estados disponibles en la lista.",
        "Choose one of the available statuses from the list.",
    )


def validate_inventory_edit(name: object, quantity: object, state: object, *, language: str = "es") -> InventoryEditValidation:
    """Validate the edit modal instantly, without external AI calls."""
    name_result = _validate_name(name)
    quantity_result = _validate_quantity(quantity)
    state_result = _validate_state(state)
    results = (name_result, quantity_result, state_result)
    messages_es = tuple(result.reason_es for result in results if not result.ok and result.reason_es)
    messages_en = tuple(result.reason_en for result in results if not result.ok and result.reason_en)
    if messages_es or messages_en:
        return InventoryEditValidation(False, "", "", "", "unknown", messages_es, messages_en)

    clean_name = name_result.value.strip()
    return InventoryEditValidation(
        True,
        clean_name,
        normalize_text(clean_name),
        quantity_result.value.strip() or "Cantidad no indicada",
        state_result.value.strip() or "unknown",
    )


def _spanish_article_for_food(clean_name: str) -> str:
    """Choose a natural Spanish article with a small local heuristic."""
    first_word = normalize_text(clean_name).split()[0] if normalize_text(clean_name).split() else "alimento"
    plural = first_word.endswith("s")
    feminine = first_word.endswith("a") or f" {first_word} " in " carne leche nata miel sal col coliflor "
    if plural and feminine:
        return "las"
    if plural:
        return "los"
    if feminine:
        return "la"
    return "el"


def build_delete_confirmation_text(item_name: str, language: str = "es") -> str:
    """Create a natural delete confirmation question without waiting for a model."""
    clean_name = _clean_text(item_name) or "este alimento"
    selected_language = str(language or "es").lower()
    if selected_language.startswith("en"):
        return f"Do you want to remove {clean_name} from your fridge?"
    return f"¿Quieres eliminar {_spanish_article_for_food(clean_name)} {clean_name} de la nevera?"
