from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import unicodedata
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Iterable

from pydantic import BaseModel, Field, field_validator

try:
    from google.genai import types
except Exception:  # pragma: no cover - keeps local tests independent from the cloud SDK
    types = None

from src.fridgechef.config import get_settings
from src.fridgechef.json_utils import extract_json_object
from src.fridgechef.llm_client import get_client
from src.fridgechef.models import (
    BarcodeObservation,
    DetectedIngredient,
    FridgeAnalysis,
    IgnoredTextFragment,
    IngredientMention,
    InventoryItem,
    RecipeItem,
    RecipeResponse,
)
from src.fridgechef.name_matching import inventory_name_key


_LOGGER = logging.getLogger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CACHE_LOCK = threading.Lock()

# These entries provide a deterministic safety net when the cloud agent is not
# available. The list intentionally contains supermarket labels, manufacturers
# and commercial range words that are commonly printed on Spanish food packs.
# The AI agent remains the primary mechanism for brands not present here.
_KNOWN_COMMERCIAL_TERMS = (
    "Alipende",
    "Realvalle",
    "El Pozo",
    "ElPozo",
    "Hacendado",
    "Carrefour",
    "Carrefour Bio",
    "Auchan",
    "Alcampo",
    "Lidl",
    "Aldi",
    "Dia",
    "Eroski",
    "Consum",
    "Bonpreu",
    "Caprabo",
    "Hipercor",
    "El Corte Inglés",
    "Nestlé",
    "Danone",
    "Kaiku",
    "Pascual",
    "Campofrío",
    "Navidul",
    "Casa Tarradellas",
    "Central Lechera Asturiana",
    "La Asturiana",
    "Gallina Blanca",
    "Gallo",
    "Buitoni",
    "Knorr",
    "Heinz",
    "Hellmann's",
    "Hellmanns",
    "Philadelphia",
    "President",
    "Président",
    "Babybel",
    "Activia",
    "Actimel",
    "Oikos",
    "Yoplait",
    "Milka",
    "Nutella",
    "Nocilla",
    "ColaCao",
    "Nesquik",
    "Kellogg's",
    "Kelloggs",
    "Special K",
    "Duroc",
)

_COMMERCIAL_PHRASES = (
    "edición limitada",
    "pack ahorro",
    "formato ahorro",
    "calidad premium",
    "selección premium",
    "receta original",
    "gama gourmet",
    "oferta especial",
)

_ALLOWED_NEW_WORDS = {
    "de",
    "del",
    "la",
    "las",
    "el",
    "los",
    "y",
    "o",
    "con",
    "sin",
    "sabor",
    "tipo",
    "estilo",
}


class FoodNameDecision(BaseModel):
    """One brand-removal decision returned by the dedicated sub-agent."""

    original_name: str
    cleaned_name: str
    is_food: bool = True
    removed_commercial_terms: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    explanation: str = ""

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, value: float) -> float:
        """Keep model confidence inside the range consumed by the guardrail."""
        return max(0.0, min(1.0, float(value or 0.0)))


class FoodNameBatch(BaseModel):
    """Structured response for one batch of manual and visual food names."""

    items: list[FoodNameDecision] = Field(default_factory=list)


class FoodNameNormalizationResult(BaseModel):
    """Validated decisions used by the input, inventory and recipe callbacks."""

    decisions: list[FoodNameDecision] = Field(default_factory=list)
    used_agent: bool = False
    warnings: list[str] = Field(default_factory=list)

    def by_original_key(self) -> dict[str, FoodNameDecision]:
        """Index decisions by a stable accent-insensitive original name."""
        return {_normalise_key(item.original_name): item for item in self.decisions}


FoodNameAgent = Callable[[list[str]], FoodNameBatch]


def _normalise_key(value: object) -> str:
    """Create a stable key without changing the user-facing food wording."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text.lower().strip())


def _clean_spacing(value: object) -> str:
    """Repair punctuation and whitespace after commercial tokens are removed."""
    text = str(value or "").replace("®", " ").replace("™", " ").replace("©", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:)])", r"\1", text)
    text = re.sub(r"([(])\s+", r"\1", text)
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\s*[-–—]\s*$", "", text)
    text = re.sub(r"\s*,\s*$", "", text)
    return text.strip(" ,.;:-")


def _term_pattern(term: str) -> re.Pattern[str]:
    """Build a Unicode-friendly, case-insensitive whole-term pattern."""
    escaped = re.escape(term.strip()).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<!\w){escaped}(?!\w)", flags=re.IGNORECASE)


def strip_commercial_terms(value: object, extra_terms: Iterable[str] = ()) -> str:
    """Remove known or agent-confirmed commercial wording from arbitrary text.

    Culinary descriptors such as cut, animal, preparation method and flavour are
    deliberately left untouched. Only explicit brands, manufacturers, retail
    labels, registered-mark symbols and promotional packaging language are removed.
    """
    text = str(value or "")
    terms = [*_KNOWN_COMMERCIAL_TERMS, *_COMMERCIAL_PHRASES, *extra_terms]
    unique_terms = sorted(
        {term.strip() for term in terms if str(term or "").strip()},
        key=len,
        reverse=True,
    )
    for term in unique_terms:
        text = _term_pattern(term).sub(" ", text)

    # Remove explicit brand labels even when the actual brand was not in the local
    # catalogue. The product description before the label remains intact.
    text = re.sub(
        r"\b(?:marca|brand|fabricado\s+por|elaborado\s+por)\s*[:\-]?\s*[\wÁÉÍÓÚÜÑáéíóúüñ&.'-]+(?:\s+[\wÁÉÍÓÚÜÑáéíóúüñ&.'-]+){0,2}",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # Pack sizes and promotional suffixes are useful for shopping, but they are not
    # part of the ingredient identity used by the fridge database or recipe agent.
    text = re.sub(
        r"(?:\s|^)(?:pack|lote|formato)\s+(?:de\s+)?\d+(?:\s*[x×]\s*\d+)?(?:\s*(?:g|kg|ml|cl|l|unidades?))?\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(?:\s|^)(?:xxl|familiar|ahorro|promoción|oferta)\b(?:\s+especial)?",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    return _clean_spacing(text)


def _local_decision(name: str) -> FoodNameDecision:
    """Create a conservative deterministic fallback for a single food name."""
    cleaned = strip_commercial_terms(name)
    removed = [term for term in _KNOWN_COMMERCIAL_TERMS if _term_pattern(term).search(name)]
    removed.extend(term for term in _COMMERCIAL_PHRASES if _term_pattern(term).search(name))
    return FoodNameDecision(
        original_name=name,
        cleaned_name=cleaned or _clean_spacing(name),
        is_food=bool(cleaned or _clean_spacing(name)),
        removed_commercial_terms=list(dict.fromkeys(removed)),
        confidence=0.72 if cleaned != _clean_spacing(name) else 0.45,
        explanation="Normalización local conservadora.",
    )


def _token_set(value: str) -> set[str]:
    """Return comparison tokens used to prevent the agent from inventing food."""
    return {
        token
        for token in re.findall(r"[\wÁÉÍÓÚÜÑáéíóúüñ]+", _normalise_key(value))
        if len(token) > 1
    }


def _validated_agent_decision(original: str, decision: FoodNameDecision) -> FoodNameDecision:
    """Apply deterministic callbacks before accepting one model decision."""
    local = _local_decision(original)
    removed_terms = [
        _clean_spacing(term)
        for term in decision.removed_commercial_terms
        if _clean_spacing(term)
    ]
    cleaned = strip_commercial_terms(decision.cleaned_name, removed_terms)

    # The normalizer may delete commercial wording, but it may not replace the food
    # with a different ingredient. This token callback blocks semantic invention.
    original_tokens = _token_set(original)
    cleaned_tokens = _token_set(cleaned)
    invented_tokens = cleaned_tokens - original_tokens - _ALLOWED_NEW_WORDS
    valid_shape = bool(cleaned) and len(cleaned) <= 180 and not invented_tokens

    # A high-confidence non-food classification is allowed to reject packaging or
    # unrelated objects. Lower-confidence rejections keep the conservative local
    # result so a temporary model ambiguity cannot delete a real ingredient.
    if not decision.is_food and decision.confidence >= 0.85:
        return decision.model_copy(
            update={
                "original_name": original,
                "cleaned_name": "",
                "removed_commercial_terms": removed_terms,
            }
        )

    if not valid_shape:
        return local

    return decision.model_copy(
        update={
            "original_name": original,
            "cleaned_name": cleaned,
            "is_food": True,
            "removed_commercial_terms": removed_terms,
        }
    )


def _database_path(settings: Any) -> Path:
    """Resolve the shared SQLite file used by the production container."""
    path = Path(settings.local_database_path)
    return path if path.is_absolute() else _PROJECT_ROOT / path


def _open_cache(settings: Any) -> sqlite3.Connection:
    """Open the persistent decision cache and create its schema when required."""
    path = _database_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS food_name_normalization_cache (
            original_key TEXT PRIMARY KEY,
            original_name TEXT NOT NULL,
            cleaned_name TEXT NOT NULL,
            is_food INTEGER NOT NULL,
            removed_terms_json TEXT NOT NULL,
            confidence REAL NOT NULL,
            source TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.commit()
    return connection


def _load_cached_decisions(settings: Any, names: list[str]) -> dict[str, FoodNameDecision]:
    """Load previous successful decisions without performing another model call."""
    keys = [_normalise_key(name) for name in names if _normalise_key(name)]
    if not keys:
        return {}

    placeholders = ",".join("?" for _ in keys)
    try:
        with _CACHE_LOCK:
            with _open_cache(settings) as connection:
                rows = connection.execute(
                    f"""
                    SELECT original_key, original_name, cleaned_name, is_food,
                           removed_terms_json, confidence
                    FROM food_name_normalization_cache
                    WHERE original_key IN ({placeholders})
                    """,
                    keys,
                ).fetchall()
    except Exception as exc:
        _LOGGER.info("Food-name cache read skipped: %s", exc)
        return {}

    result: dict[str, FoodNameDecision] = {}
    for key, original, cleaned, is_food, removed_json, confidence in rows:
        try:
            removed = json.loads(removed_json)
        except Exception:
            removed = []
        result[str(key)] = FoodNameDecision(
            original_name=str(original),
            cleaned_name=str(cleaned),
            is_food=bool(is_food),
            removed_commercial_terms=[str(term) for term in removed if str(term).strip()],
            confidence=float(confidence or 0.0),
            explanation="Decisión recuperada de SQLite.",
        )
    return result


def _save_cached_decisions(settings: Any, decisions: Iterable[FoodNameDecision], source: str) -> None:
    """Persist validated decisions so refreshes do not consume additional quota."""
    rows = []
    for decision in decisions:
        key = _normalise_key(decision.original_name)
        if not key:
            continue
        rows.append(
            (
                key,
                decision.original_name,
                decision.cleaned_name,
                int(decision.is_food),
                json.dumps(decision.removed_commercial_terms, ensure_ascii=False),
                decision.confidence,
                source,
            )
        )
    if not rows:
        return

    try:
        with _CACHE_LOCK:
            with _open_cache(settings) as connection:
                connection.executemany(
                    """
                    INSERT INTO food_name_normalization_cache (
                        original_key, original_name, cleaned_name, is_food,
                        removed_terms_json, confidence, source
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(original_key) DO UPDATE SET
                        original_name = excluded.original_name,
                        cleaned_name = excluded.cleaned_name,
                        is_food = excluded.is_food,
                        removed_terms_json = excluded.removed_terms_json,
                        confidence = excluded.confidence,
                        source = excluded.source,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    rows,
                )
                connection.commit()
    except Exception as exc:
        _LOGGER.info("Food-name cache write skipped: %s", exc)


def _model_candidates(settings: Any) -> list[str]:
    """Build the same bounded primary/fallback chain used by the other agents."""
    values = [settings.model_name]
    values.extend(
        part.strip()
        for part in str(getattr(settings, "text_fallback_models", "")).split(",")
        if part.strip()
    )
    return list(dict.fromkeys(value for value in values if value))


def _agent_prompt(names: list[str]) -> str:
    """Build the strict commercial-name removal contract for Gemini."""
    return f"""
Eres el agente especializado en normalización de nombres de alimentos de FridgeChef AI Assistant.

Objetivo:
Recibir nombres obtenidos mediante texto, fotografías o datos persistidos y devolver el nombre culinario completo de cada alimento, sin marcas, fabricantes, supermercados, gamas comerciales, eslóganes, tamaños de envase ni palabras promocionales.

Reglas obligatorias:
- Conserva toda la información culinaria útil: tipo de alimento, animal, corte, formato, preparación, ahumado, natural, extrafino, sabor, relleno, variedad culinaria y estado cuando forme parte real del producto.
- Elimina marcas y aspectos comerciales aunque aparezcan en medio del nombre o al final.
- No inventes ni sustituyas un alimento por otro.
- Si la entrada no es un alimento real, marca is_food=false.
- No incluyas la marca dentro de cleaned_name.
- removed_commercial_terms debe enumerar únicamente lo eliminado por ser comercial.
- Devuelve todos los elementos de entrada una sola vez y en el mismo orden.
- Devuelve únicamente JSON válido.

Ejemplos:
- "Bacon en tiras ahumado natural Realvalle" -> "Bacon en tiras ahumado natural".
- "Filetes finos de lomo de cerdo Duroc El Pozo" -> "Filetes finos de lomo de cerdo".
- "Yogur griego Alipende (sabor miel y nueces)" -> "Yogur griego (sabor miel y nueces)".
- "Filetes de pechuga extrafinos de pollo Alipende" -> "Filetes de pechuga extrafinos de pollo".
- "Piña o maíz troceado" se mantiene sin cambios.

Nombres de entrada:
{json.dumps(names, ensure_ascii=False, indent=2)}

Estructura obligatoria:
{{
  "items": [
    {{
      "original_name": "nombre exacto de entrada",
      "cleaned_name": "nombre culinario sin marca ni contenido comercial",
      "is_food": true,
      "removed_commercial_terms": ["marca o término comercial eliminado"],
      "confidence": 0.0,
      "explanation": "explicación breve en español"
    }}
  ]
}}
"""


def _run_cloud_agent(names: list[str]) -> FoodNameBatch:
    """Run one structured, retry-enabled batch request through Vertex AI."""
    if types is None:
        raise RuntimeError("google-genai types are not available in this environment.")

    settings = get_settings()
    prompt = _agent_prompt(names)
    last_error: Exception | None = None

    for model_name in _model_candidates(settings):
        try:
            client = get_client()
            try:
                config = types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                    response_schema=FoodNameBatch,
                )
            except Exception:
                config = types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                )

            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
            parsed = getattr(response, "parsed", None)
            if isinstance(parsed, FoodNameBatch):
                return parsed
            if isinstance(parsed, dict):
                return FoodNameBatch.model_validate(parsed)
            return FoodNameBatch.model_validate(extract_json_object(response.text or ""))
        except Exception as exc:
            last_error = exc
            _LOGGER.info(
                "Food-name normalizer candidate unavailable for %s: %s",
                model_name,
                " ".join(str(exc).split())[:280],
            )

    if last_error is not None:
        raise last_error
    raise RuntimeError("No text model is configured for the food-name normalizer.")


def normalize_food_names(
    names: Iterable[str],
    *,
    agent: FoodNameAgent | None = None,
    use_cache: bool = True,
) -> FoodNameNormalizationResult:
    """Normalize one complete action batch with cache, agent and local fallback."""
    ordered_names: list[str] = []
    seen: set[str] = set()
    for raw_name in names:
        name = _clean_spacing(raw_name)
        key = _normalise_key(name)
        if name and key not in seen:
            ordered_names.append(name)
            seen.add(key)

    if not ordered_names:
        return FoodNameNormalizationResult()

    settings = get_settings()
    cached = _load_cached_decisions(settings, ordered_names) if use_cache else {}
    missing = [name for name in ordered_names if _normalise_key(name) not in cached]
    fresh: dict[str, FoodNameDecision] = {}
    warnings: list[str] = []
    used_agent = False

    if missing:
        try:
            batch = agent(missing) if agent else _run_cloud_agent(missing)
            used_agent = True
            returned = {_normalise_key(item.original_name): item for item in batch.items}
            for original in missing:
                raw_decision = returned.get(_normalise_key(original))
                fresh[_normalise_key(original)] = (
                    _validated_agent_decision(original, raw_decision)
                    if raw_decision is not None
                    else _local_decision(original)
                )
            if use_cache:
                _save_cached_decisions(settings, fresh.values(), "agent")
        except Exception as exc:
            warnings.append("commercial_name_agent_unavailable")
            _LOGGER.info(
                "Food-name normalizer used its deterministic fallback: %s",
                " ".join(str(exc).split())[:280],
            )
            for original in missing:
                decision = _local_decision(original)
                fresh[_normalise_key(original)] = decision
            if use_cache:
                # Cache only deterministic changes. Unchanged names are retried by the
                # agent in a future action instead of becoming permanently unverified.
                changed = [
                    decision
                    for decision in fresh.values()
                    if _normalise_key(decision.cleaned_name) != _normalise_key(decision.original_name)
                ]
                _save_cached_decisions(settings, changed, "local")

    decisions = [
        cached.get(_normalise_key(name))
        or fresh.get(_normalise_key(name))
        or _local_decision(name)
        for name in ordered_names
    ]
    return FoodNameNormalizationResult(
        decisions=decisions,
        used_agent=used_agent,
        warnings=warnings,
    )


def _decision_for(name: str, decisions: dict[str, FoodNameDecision]) -> FoodNameDecision:
    """Return one validated decision, falling back locally for missing values."""
    return decisions.get(_normalise_key(name)) or _local_decision(name)


def _clean_free_text(value: object, removed_terms: Iterable[str]) -> str:
    """Remove learned commercial terms from evidence, notes and recipe prose."""
    return strip_commercial_terms(value, removed_terms)


def sanitize_action_inputs(
    parse_result: Any,
    image_results: list[tuple[str, FridgeAnalysis]],
    *,
    agent: FoodNameAgent | None = None,
) -> tuple[Any, list[tuple[str, FridgeAnalysis]], FoodNameNormalizationResult]:
    """Normalize all text and image names once for Analyze and Generate actions."""
    names: list[str] = [item.name for item in parse_result.accepted_items]
    for _, analysis in image_results:
        names.extend(item.name for item in analysis.visible_ingredients)
        names.extend(item.name for item in analysis.possible_spoiled_items)
        names.extend(analysis.uncertain_items)
        names.extend(
            observation.product_name_guess
            for observation in analysis.barcode_observations
            if observation.product_name_guess
        )

    result = normalize_food_names(names, agent=agent)
    decisions = result.by_original_key()
    all_removed_terms = [
        term
        for decision in result.decisions
        for term in decision.removed_commercial_terms
    ]

    accepted_items: list[IngredientMention] = []
    rejected_fragments = list(parse_result.ignored_fragments)
    for item in parse_result.accepted_items:
        decision = _decision_for(item.name, decisions)
        if not decision.is_food or not decision.cleaned_name:
            rejected_fragments.append(
                IgnoredTextFragment(
                    text=item.source_text or item.name,
                    reason="No parece un alimento real de la nevera.",
                )
            )
            continue
        accepted_items.append(
            item.model_copy(
                update={
                    "name": decision.cleaned_name,
                    # The raw commercial product wording must not reappear in the
                    # visible inventory notes after the name itself was normalized.
                    "source_text": "",
                    "notes": [
                        _clean_free_text(note, decision.removed_commercial_terms)
                        for note in item.notes
                        if _clean_free_text(note, decision.removed_commercial_terms)
                    ],
                }
            )
        )

    cleaned_parse_result = replace(
        parse_result,
        accepted=[item.name for item in accepted_items],
        ignored=[fragment.text for fragment in rejected_fragments],
        accepted_items=accepted_items,
        ignored_fragments=rejected_fragments,
        agent_notes=[*parse_result.agent_notes, "commercial_name_normalizer"],
    )

    cleaned_image_results: list[tuple[str, FridgeAnalysis]] = []
    for source, analysis in image_results:
        visible: list[DetectedIngredient] = []
        for item in analysis.visible_ingredients:
            decision = _decision_for(item.name, decisions)
            if decision.is_food and decision.cleaned_name:
                visible.append(
                    item.model_copy(
                        update={
                            "name": decision.cleaned_name,
                            "evidence": _clean_free_text(
                                item.evidence,
                                decision.removed_commercial_terms,
                            ) or None,
                        }
                    )
                )

        spoiled: list[DetectedIngredient] = []
        for item in analysis.possible_spoiled_items:
            decision = _decision_for(item.name, decisions)
            if decision.is_food and decision.cleaned_name:
                spoiled.append(
                    item.model_copy(
                        update={
                            "name": decision.cleaned_name,
                            "evidence": _clean_free_text(
                                item.evidence,
                                decision.removed_commercial_terms,
                            ) or None,
                        }
                    )
                )

        uncertain: list[str] = []
        for name in analysis.uncertain_items:
            decision = _decision_for(name, decisions)
            if decision.is_food and decision.cleaned_name:
                uncertain.append(decision.cleaned_name)

        observations: list[BarcodeObservation] = []
        for observation in analysis.barcode_observations:
            product_guess = observation.product_name_guess or ""
            decision = _decision_for(product_guess, decisions) if product_guess else None
            observations.append(
                observation.model_copy(
                    update={
                        "product_name_guess": (
                            decision.cleaned_name
                            if decision and decision.is_food and decision.cleaned_name
                            else None
                        ),
                        "notes": [
                            _clean_free_text(note, all_removed_terms)
                            for note in observation.notes
                            if _clean_free_text(note, all_removed_terms)
                        ],
                    }
                )
            )

        cleaned_image_results.append(
            (
                source,
                analysis.model_copy(
                    update={
                        "visible_ingredients": visible,
                        "possible_spoiled_items": spoiled,
                        "uncertain_items": list(dict.fromkeys(uncertain)),
                        "barcode_observations": observations,
                        "notes": [
                            _clean_free_text(note, all_removed_terms)
                            for note in analysis.notes
                            if _clean_free_text(note, all_removed_terms)
                        ],
                    }
                ),
            )
        )

    return cleaned_parse_result, cleaned_image_results, result


def sanitize_inventory_items(
    items: Iterable[InventoryItem],
    *,
    agent: FoodNameAgent | None = None,
) -> tuple[list[InventoryItem], FoodNameNormalizationResult]:
    """Migrate persisted inventory names while preserving every non-name field."""
    inventory = list(items)
    result = normalize_food_names((item.name for item in inventory), agent=agent)
    decisions = result.by_original_key()
    cleaned: list[InventoryItem] = []

    for item in inventory:
        decision = _decision_for(item.name, decisions)
        if not decision.is_food or not decision.cleaned_name:
            continue
        cleaned.append(
            item.model_copy(
                update={
                    "name": decision.cleaned_name,
                    "normalized_name": inventory_name_key(decision.cleaned_name),
                    "notes": [
                        _clean_free_text(note, decision.removed_commercial_terms)
                        for note in item.notes
                        if _clean_free_text(note, decision.removed_commercial_terms)
                    ],
                }
            )
        )

    return cleaned, result


def _cached_removed_terms() -> list[str]:
    """Return learned brand terms for the final recipe-output callback."""
    settings = get_settings()
    try:
        with _CACHE_LOCK:
            with _open_cache(settings) as connection:
                rows = connection.execute(
                    "SELECT removed_terms_json FROM food_name_normalization_cache"
                ).fetchall()
    except Exception:
        return []

    terms: list[str] = []
    for row in rows:
        try:
            values = json.loads(row[0])
        except Exception:
            values = []
        terms.extend(str(value) for value in values if str(value).strip())
    return list(dict.fromkeys(terms))


def sanitize_recipe_response(response: RecipeResponse) -> RecipeResponse:
    """Final callback preventing learned brands from reappearing in recipes."""
    removed_terms = _cached_removed_terms()

    def clean(value: object) -> str:
        return _clean_free_text(value, removed_terms)

    recipes: list[RecipeItem] = []
    for recipe in response.recipes:
        recipes.append(
            recipe.model_copy(
                update={
                    "title": clean(recipe.title),
                    "description": clean(recipe.description),
                    "why_this_recipe": clean(recipe.why_this_recipe),
                    "ingredients_used": [
                        clean(item) for item in recipe.ingredients_used if clean(item)
                    ],
                    "missing_required_for_target": [
                        clean(item)
                        for item in recipe.missing_required_for_target
                        if clean(item)
                    ],
                    "missing_optional": [
                        clean(item) for item in recipe.missing_optional if clean(item)
                    ],
                    "steps": [clean(step) for step in recipe.steps if clean(step)],
                    "anti_waste_tip": clean(recipe.anti_waste_tip),
                    "allergen_alerts": [
                        clean(note) for note in recipe.allergen_alerts if clean(note)
                    ],
                    "nutrition_notes": [
                        clean(note) for note in recipe.nutrition_notes if clean(note)
                    ],
                    "shopping_list": [
                        clean(item) for item in recipe.shopping_list if clean(item)
                    ],
                }
            )
        )

    return response.model_copy(
        update={
            "recipes": recipes,
            "global_explanation": clean(response.global_explanation),
            "safety_notes": [clean(note) for note in response.safety_notes if clean(note)],
            "save_recommendation": clean(response.save_recommendation),
            "recognized_ingredients": [
                clean(item) for item in response.recognized_ingredients if clean(item)
            ],
        }
    )
