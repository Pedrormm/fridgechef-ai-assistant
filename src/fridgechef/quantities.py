from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping


QuantityParts = dict[str, float]

_UNKNOWN_LABELS = {
    "",
    "cantidad no indicada",
    "quantity not specified",
    "not specified",
    "unknown",
    "desconocida",
    "desconocido",
}

_UNIT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("kg", (r"\bkg\b", r"\bkilos?\b", r"\bkilogramos?\b", r"\bkilograms?\b")),
    ("g", (r"\bgr\b", r"\bg\b", r"\bgramos?\b", r"\bgrams?\b")),
    ("l", (r"\bl\b", r"\blitros?\b", r"\blitres?\b", r"\bliters?\b")),
    ("ml", (r"\bml\b", r"\bmililitros?\b", r"\bmillilitres?\b", r"\bmilliliters?\b")),
    ("can", (r"\blatas?\b", r"\bcans?\b")),
    ("bottle", (r"\bbotellas?\b", r"\bbottles?\b")),
    ("jar", (r"\bbotes?\b", r"\btarros?\b", r"\bfrascos?\b", r"\bjars?\b")),
    ("pack", (r"\bpaquetes?\b", r"\bpacks?\b", r"\bpackages?\b")),
    ("slice", (r"\blonchas?\b", r"\brebanadas?\b", r"\bslices?\b")),
    ("bunch", (r"\bmanojos?\b", r"\bbunch(?:es)?\b")),
    ("clove", (r"\bdientes?\b", r"\bcloves?\b")),
    ("cup", (r"\btazas?\b", r"\bcups?\b")),
    ("tablespoon", (r"\bcucharadas?\b", r"\btablespoons?\b", r"\btbsp\b")),
    ("teaspoon", (r"\bcucharaditas?\b", r"\bteaspoons?\b", r"\btsp\b")),
    ("unit", (r"\bunidades?\b", r"\buds?\b", r"\bpiezas?\b", r"\bunits?\b", r"\bitems?\b")),
)

_WORD_AMOUNTS: tuple[tuple[str, float], ...] = (
    (r"\bmedia docena\b|\bhalf a dozen\b", 6.0),
    (r"\buna docena\b|\bone dozen\b|\bdocena\b|\bdozen\b", 12.0),
    (r"\bun par\b|\ba pair\b", 2.0),
    (r"\bmedio\b|\bmedia\b|\bhalf\b", 0.5),
    (r"\buna?\b|\bone\b", 1.0),
    (r"\bdos\b|\btwo\b", 2.0),
    (r"\btres\b|\bthree\b", 3.0),
    (r"\bcuatro\b|\bfour\b", 4.0),
    (r"\bcinco\b|\bfive\b", 5.0),
    (r"\bseis\b|\bsix\b", 6.0),
    (r"\bsiete\b|\bseven\b", 7.0),
    (r"\bocho\b|\beight\b", 8.0),
    (r"\bnueve\b|\bnine\b", 9.0),
    (r"\bdiez\b|\bten\b", 10.0),
)


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text.lower().strip())


def _amount_from_text(text: str) -> float | None:
    number_match = re.search(r"(?<!\w)(\d+(?:[.,]\d+)?)", text)
    if number_match:
        return float(number_match.group(1).replace(",", "."))
    for pattern, amount in _WORD_AMOUNTS:
        if re.search(pattern, text):
            return amount
    return None


def _unit_from_text(text: str) -> str:
    for unit, patterns in _UNIT_PATTERNS:
        if any(re.search(pattern, text) for pattern in patterns):
            return unit
    return "unit"


def parse_quantity_label(label: object) -> QuantityParts:
    """Convert a user or model quantity label into canonical additive parts."""
    normalized = _normalize(label)
    if normalized in _UNKNOWN_LABELS:
        return {"unit": 1.0}

    amount = _amount_from_text(normalized)
    if amount is None or amount <= 0:
        return {"unit": 1.0}

    unit = _unit_from_text(normalized)
    if unit == "kg":
        return {"g": amount * 1000.0}
    if unit == "l":
        return {"ml": amount * 1000.0}
    return {unit: amount}


def normalize_quantity_parts(parts: Mapping[str, object] | None, fallback_label: object = None) -> QuantityParts:
    """Validate persisted quantity parts and migrate legacy quantity labels."""
    result: QuantityParts = {}
    for raw_unit, raw_amount in (parts or {}).items():
        unit = str(raw_unit or "").strip()
        if not unit:
            continue
        try:
            amount = float(raw_amount)
        except (TypeError, ValueError):
            continue
        if amount > 0:
            result[unit] = result.get(unit, 0.0) + amount
    return result or parse_quantity_label(fallback_label)


def merge_quantity_parts(
    existing: Mapping[str, object] | None,
    incoming: Mapping[str, object] | None,
    *,
    mode: str,
) -> QuantityParts:
    """Sum separate inputs or deduplicate repeated detections from one input."""
    left = normalize_quantity_parts(existing)
    right = normalize_quantity_parts(incoming)
    keys = set(left) | set(right)
    if mode == "sum":
        return {key: left.get(key, 0.0) + right.get(key, 0.0) for key in keys}
    return {key: max(left.get(key, 0.0), right.get(key, 0.0)) for key in keys}


def _format_number(value: float, language: str) -> str:
    rounded = round(float(value), 3)
    if abs(rounded - round(rounded)) < 1e-9:
        return str(int(round(rounded)))
    text = f"{rounded:.3f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") if language.startswith("es") else text


def _unit_label(unit: str, amount: float, language: str) -> str:
    singular = abs(amount - 1.0) < 1e-9
    labels_es = {
        "unit": ("unidad", "unidades"),
        "g": ("gramo", "gramos"),
        "ml": ("mililitro", "mililitros"),
        "can": ("lata", "latas"),
        "bottle": ("botella", "botellas"),
        "jar": ("bote", "botes"),
        "pack": ("paquete", "paquetes"),
        "slice": ("loncha", "lonchas"),
        "bunch": ("manojo", "manojos"),
        "clove": ("diente", "dientes"),
        "cup": ("taza", "tazas"),
        "tablespoon": ("cucharada", "cucharadas"),
        "teaspoon": ("cucharadita", "cucharaditas"),
    }
    labels_en = {
        "unit": ("unit", "units"),
        "g": ("gram", "grams"),
        "ml": ("millilitre", "millilitres"),
        "can": ("can", "cans"),
        "bottle": ("bottle", "bottles"),
        "jar": ("jar", "jars"),
        "pack": ("pack", "packs"),
        "slice": ("slice", "slices"),
        "bunch": ("bunch", "bunches"),
        "clove": ("clove", "cloves"),
        "cup": ("cup", "cups"),
        "tablespoon": ("tablespoon", "tablespoons"),
        "teaspoon": ("teaspoon", "teaspoons"),
    }
    labels = labels_es if language.startswith("es") else labels_en
    pair = labels.get(unit, (unit, unit))
    return pair[0] if singular else pair[1]


def format_quantity_parts(parts: Mapping[str, object] | None, language: str = "es") -> str:
    """Create a stable Spanish or English label from canonical quantity parts."""
    normalized = normalize_quantity_parts(parts)
    rendered: list[str] = []
    order = (
        "unit",
        "g",
        "ml",
        "can",
        "bottle",
        "jar",
        "pack",
        "slice",
        "bunch",
        "clove",
        "cup",
        "tablespoon",
        "teaspoon",
    )
    for unit in [*order, *sorted(set(normalized) - set(order))]:
        amount = normalized.get(unit)
        if amount is None or amount <= 0:
            continue
        display_amount = amount
        display_unit = unit
        if unit == "g" and amount >= 1000:
            display_amount = amount / 1000.0
            display_unit = "kg"
        elif unit == "ml" and amount >= 1000:
            display_amount = amount / 1000.0
            display_unit = "l"

        if display_unit == "kg":
            unit_text = "kg"
        elif display_unit == "l":
            if language.startswith("es"):
                unit_text = "litro" if abs(display_amount - 1.0) < 1e-9 else "litros"
            else:
                unit_text = "litre" if abs(display_amount - 1.0) < 1e-9 else "litres"
        else:
            unit_text = _unit_label(display_unit, display_amount, language)
        rendered.append(f"{_format_number(display_amount, language)} {unit_text}")
    if rendered:
        return " + ".join(rendered)
    return "1 unidad" if language.startswith("es") else "1 unit"


def display_quantity_label(parts: Mapping[str, object] | None, legacy_label: object, language: str = "es") -> str:
    """Display structured quantities while remaining compatible with legacy rows."""
    return format_quantity_parts(normalize_quantity_parts(parts, legacy_label), language)
