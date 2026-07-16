from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Iterable

try:
    from google.genai import types
except Exception:  # pragma: no cover - allows local tests without google-genai installed
    types = None

from src.fridgechef.config import get_settings
from src.fridgechef.json_utils import extract_json_object
from src.fridgechef.llm_client import get_client
from src.fridgechef.models import IgnoredTextFragment, IngredientMention, ManualIngredientExtraction
from src.fridgechef.spanish_guard import ensure_manual_extraction_spanish

logger = logging.getLogger(__name__)


def _clean_manual_extraction(extraction: ManualIngredientExtraction) -> ManualIngredientExtraction:
    """Apply the local display-safety guard without launching another model call."""
    return ensure_manual_extraction_spanish(
        extraction,
        agent=lambda payload, _context: payload,
    )


@dataclass(frozen=True)
class GroundingResult:
    """Google Search context and optional complete extraction for manual input."""

    used: bool = False
    notes: str = ""
    search_queries: list[str] = field(default_factory=list)
    extraction: ManualIngredientExtraction | None = None


@dataclass(frozen=True)
class ManualIngredientParseResult:
    """Validated manual input split into food items and rejected text fragments."""

    accepted: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)
    accepted_items: list[IngredientMention] = field(default_factory=list)
    ignored_fragments: list[IgnoredTextFragment] = field(default_factory=list)
    agent_notes: list[str] = field(default_factory=list)
    used_agent: bool = False
    search_used: bool = False
    search_queries: list[str] = field(default_factory=list)

    @property
    def has_food(self) -> bool:
        """Return whether at least one usable food-related fragment was found."""
        return bool(self.accepted_items or self.accepted)


Extractor = Callable[[str, list[str]], ManualIngredientExtraction]


def normalize_text(value: str) -> str:
    """Normalize accents, casing and spacing for stable comparisons."""
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = re.sub(r"\s+", " ", normalized.lower().strip())
    return normalized


def clean_fragment(value: str) -> str:
    """Clean spacing and external punctuation without changing the user's wording."""
    value = re.sub(r"^[\s\-•*]+", "", value or "")
    value = re.sub(r"[\s!?]+$", "", value)
    return re.sub(r"\s+", " ", value).strip(" ,.;:")


def unique_preserving_order(items: Iterable[str]) -> list[str]:
    """Deduplicate fragments without changing their display order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        clean = clean_fragment(item)
        key = normalize_text(clean)
        if clean and key not in seen:
            result.append(clean)
            seen.add(key)
    return result


def split_user_text(text: str) -> list[str]:
    """Split free text into short reviewable fragments."""
    if not text or not text.strip():
        return []

    normalized = text.replace("\r", "\n")
    coarse_parts = re.split(r"[\n;|]+|(?<=[.!?])\s+", normalized)
    fragments: list[str] = []
    for part in coarse_parts:
        part = clean_fragment(part)
        if not part:
            continue
        fragments.extend(clean_fragment(chunk) for chunk in part.split(",") if clean_fragment(chunk))
    return unique_preserving_order(fragments)


def _agent_unavailable_extraction(fragments: list[str]) -> ManualIngredientExtraction:
    """Return a safe result when every configured AI model is unavailable."""
    return ManualIngredientExtraction(
        accepted=[],
        ignored=[
            IgnoredTextFragment(
                text=fragment,
                reason="No he podido revisar este texto con el agente de comprensión. Inténtalo de nuevo en unos segundos.",
            )
            for fragment in fragments
        ],
        reasoning_summary="No se ha realizado clasificación local porque la decisión semántica corresponde al agente de IA.",
        agent_notes=["semantic_agent_unavailable"],
    )


def _contains_ambiguous_reference(text: str, fragments: list[str]) -> bool:
    """Detect names, links and cultural references that benefit from web context."""
    if re.search(r'https?://|www\.|[@#]|["“”«»]', text or "", flags=re.IGNORECASE):
        return True

    normalized = normalize_text(text)
    reference_markers = (
        "se llama",
        "conocido como",
        "personaje",
        "famos",
        "meme",
        "pelicula",
        "serie",
        "marca",
        "pokemon",
        "videojuego",
        "artista",
        "cantante",
        "actor",
        "deportista",
    )
    if any(marker in normalized for marker in reference_markers):
        return True

    for fragment in fragments:
        words = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9][\wÁÉÍÓÚÜÑáéíóúüñ-]*", fragment)
        for index, word in enumerate(words):
            if index > 0 and (word[:1].isupper() or (len(word) > 1 and word.isupper())):
                return True
    return False


def _needs_search_grounding(
    text: str,
    fragments: list[str],
    mode: str = "multiple_or_ambiguous",
    min_fragments: int = 2,
) -> bool:
    """Choose whether manual input must be checked with Google Search.

    The default deliberately grounds every multi-fragment list in one combined
    request. This lets the agent distinguish food from names, jokes and unrelated
    objects without launching one search request per fragment.
    """
    normalized_mode = (mode or "multiple_or_ambiguous").strip().lower()
    if normalized_mode == "off":
        return False
    if normalized_mode == "always":
        return True

    ambiguous = _contains_ambiguous_reference(text, fragments)
    if normalized_mode == "ambiguous":
        return ambiguous

    return len(fragments) >= max(2, min_fragments) or ambiguous


def _model_candidates(primary_model: str, fallback_models: str) -> list[str]:
    """Build a deduplicated model fallback chain."""
    candidates: list[str] = []
    for value in [primary_model, *fallback_models.split(",")]:
        model = str(value or "").strip()
        if model and model not in candidates:
            candidates.append(model)
    return candidates


def _is_retryable_error(exc: Exception) -> bool:
    """Identify capacity and transient service failures after SDK retries."""
    code = getattr(exc, "code", None)
    try:
        if int(code) in {408, 429, 500, 502, 503, 504}:
            return True
    except (TypeError, ValueError):
        pass

    message = str(exc).upper()
    return any(
        marker in message
        for marker in (
            "RESOURCE_EXHAUSTED",
            "TOO MANY REQUESTS",
            "SERVICE_UNAVAILABLE",
            "DEADLINE_EXCEEDED",
            "INTERNAL SERVER ERROR",
            "BAD GATEWAY",
            "GATEWAY TIMEOUT",
        )
    )


def _search_queries_from_response(response) -> list[str]:
    """Read Google Search Suggestions from Gen AI SDK response metadata."""
    try:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return []
        metadata = getattr(candidates[0], "grounding_metadata", None)
        if metadata is None:
            return []
        queries = getattr(metadata, "web_search_queries", None)
        if queries is None and isinstance(metadata, dict):
            queries = metadata.get("webSearchQueries") or metadata.get("web_search_queries")
        return unique_preserving_order(str(query) for query in (queries or []))
    except Exception:
        return []


def _manual_extraction_prompt(text: str, fragments: list[str], grounding_notes: str = "") -> str:
    """Build the shared extraction contract for grounded and normal requests."""
    return f"""
Eres el agente de comprensión de texto de FridgeChef AI Assistant.

Objetivo:
Extrae únicamente alimentos reales que el usuario afirma tener disponibles.

Reglas:
- Comprende lenguaje natural en español o inglés.
- Evalúa todos los fragmentos de forma conjunta.
- Conserva la cantidad de cada alimento.
- Conserva el estado indicado por el usuario.
- Devuelve el nombre culinario completo sin marcas, fabricantes, supermercados, gamas comerciales, eslóganes, tamaños de envase ni palabras promocionales.
- Conserva detalles útiles como corte, animal, formato, preparación, ahumado, natural, extrafino y sabor.
- Separa el estado del nombre: "5 tomates podridos" debe producir nombre "tomates", cantidad "5 unidades" y estado "spoiled".
- Rechaza objetos, comentarios, bromas, nombres propios y referencias culturales aunque contengan el nombre de un animal o alimento.
- "El pulpo Paul" es una referencia cultural y no un ingrediente disponible.
- "Una bombilla", "los ingleses no saben nada" y "todo pa atrás" no son alimentos.
- No inventes cantidades ni estados.
- Usa exactamente uno de estos estados internos:
  * fresh: el usuario dice que está fresco o en buen estado.
  * aging: está maduro, pasado o conviene usarlo pronto, pero no afirma que esté estropeado.
  * possible_spoiled: hay dudas o signos posibles de deterioro.
  * spoiled: el usuario afirma que está podrido, caducado o estropeado.
  * unknown: no se indica el estado.
- Todos los textos visibles deben estar en español de España.
- Devuelve solo un objeto JSON válido.

Texto completo:
{text}

Fragmentos:
{json.dumps(fragments, ensure_ascii=False, indent=2)}

Contexto obtenido mediante Google Search:
{grounding_notes or "Sin notas adicionales."}

Estructura obligatoria:
{{
  "accepted": [
    {{
      "name": "nombre del alimento sin cantidad ni adjetivo de estado",
      "quantity_label": "cantidad clara en español, o Cantidad no indicada",
      "state": "fresh|aging|possible_spoiled|spoiled|unknown",
      "source_text": "fragmento exacto del usuario",
      "confidence": 0.0,
      "notes": ["explicación breve en español"]
    }}
  ],
  "ignored": [
    {{"text": "fragmento ignorado", "reason": "motivo amable en español"}}
  ],
  "reasoning_summary": "resumen breve en español",
  "agent_notes": ["manual_input_agent"]
}}

Ejemplo:
Entrada: "5 tomates podridos, 1 pepino, 4 patatas, el pulpo Paul, una bombilla, los ingleses no saben nada, alcachofa, todo pa atrás, filete de ternera"
Resultado esperado:
- Aceptar tomates, pepino, patatas, alcachofa y filete de ternera.
- Tomates: cantidad "5 unidades" y estado "spoiled".
- Pepino: cantidad "1 unidad".
- Patatas: cantidad "4 unidades".
- Alcachofa y filete de ternera: "Cantidad no indicada".
- Ignorar el pulpo Paul, la bombilla y los comentarios.
"""


def _ground_manual_input(
    text: str,
    fragments: list[str],
    model_names: list[str],
) -> GroundingResult:
    """Use one Google-grounded request for an entire mixed manual list.

    The grounded response is asked to perform the full extraction. If it returns
    valid JSON, no second model call is needed. If it returns useful prose instead,
    that prose becomes context for the normal structured-output request.
    """
    settings = get_settings()
    if not settings.manual_grounding_enabled:
        return GroundingResult()
    if not _needs_search_grounding(
        text,
        fragments,
        mode=getattr(settings, "manual_grounding_mode", "multiple_or_ambiguous"),
        min_fragments=getattr(settings, "manual_grounding_min_fragments", 2),
    ):
        return GroundingResult()

    if types is None:
        raise RuntimeError("google-genai types are not available in this environment.")

    client = get_client()
    prompt = _manual_extraction_prompt(text, fragments)

    last_error: Exception | None = None
    for model_name in model_names:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=1.0,
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            )
            response_text = response.text or ""
            queries = _search_queries_from_response(response)
            try:
                data = extract_json_object(response_text)
                extraction = _clean_manual_extraction(
                    ManualIngredientExtraction.model_validate(data)
                )
                return GroundingResult(
                    used=True,
                    notes=response_text,
                    search_queries=queries,
                    extraction=extraction,
                )
            except Exception as parse_exc:
                logger.info(
                    "La respuesta con Google Search se usará como contexto porque no era JSON estructurado: %s",
                    parse_exc,
                )
                return GroundingResult(
                    used=True,
                    notes=response_text,
                    search_queries=queries,
                )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "El modelo %s no pudo completar la comprobación con Google Search: %s",
                model_name,
                exc,
            )
            # The client has already applied exponential backoff. Move to the
            # next model instead of repeating the same request immediately.
            continue

    if last_error is not None:
        logger.warning(
            "Google Search no estuvo disponible tras probar todos los modelos; "
            "se continuará con la extracción estructurada sin grounding: %s",
            last_error,
        )
    return GroundingResult()


def _generate_json_from_prompt(client, model_names: list[str], prompt: str) -> dict:
    """Ask Gemini for JSON with exponential backoff and model failover.

    HTTP retries are handled by the Gen AI client. This function avoids retry
    amplification: after a transient error survives those retries, it changes to
    the next configured model rather than issuing the same request immediately.
    """
    last_error: Exception | None = None

    for model_name in model_names:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )
            return extract_json_object(response.text or "")
        except Exception as exc:
            last_error = exc
            if _is_retryable_error(exc):
                logger.warning(
                    "El modelo %s sigue sin capacidad tras los reintentos exponenciales; "
                    "se probará el siguiente modelo: %s",
                    model_name,
                    exc,
                )
                continue

            logger.warning(
                "El modelo %s no aceptó el modo JSON; se reintenta una vez en modo texto: %s",
                model_name,
                exc,
            )
            try:
                fallback_prompt = (
                    prompt
                    + "\n\nImportante: responde únicamente con el objeto JSON solicitado, sin texto antes ni después."
                )
                response = client.models.generate_content(
                    model=model_name,
                    contents=fallback_prompt,
                    config=types.GenerateContentConfig(temperature=0.0),
                )
                return extract_json_object(response.text or "")
            except Exception as fallback_exc:
                last_error = fallback_exc
                logger.warning("El modelo %s también falló en modo texto: %s", model_name, fallback_exc)

    if last_error is not None:
        raise last_error
    raise RuntimeError("No hay modelos de texto configurados para el agente de comprensión.")


def _agentic_extraction(
    text: str,
    fragments: list[str],
) -> tuple[ManualIngredientExtraction, GroundingResult]:
    """Run grounded or structured language understanding for manual fridge text."""
    if types is None:
        raise RuntimeError("google-genai types are not available in this environment.")

    settings = get_settings()
    models = _model_candidates(settings.model_name, settings.text_fallback_models)
    grounding = _ground_manual_input(text, fragments, models)

    if grounding.extraction is not None:
        return grounding.extraction, grounding

    client = get_client()
    prompt = _manual_extraction_prompt(text, fragments, grounding.notes)
    data = _generate_json_from_prompt(client, models, prompt)
    extraction = _clean_manual_extraction(
        ManualIngredientExtraction.model_validate(data)
    )
    return extraction, grounding


def _to_parse_result(
    extraction: ManualIngredientExtraction,
    used_agent: bool,
    grounding: GroundingResult | None = None,
) -> ManualIngredientParseResult:
    """Convert structured agent output into the stable public return type."""
    accepted_items = []
    seen: set[str] = set()
    for item in extraction.accepted:
        name = clean_fragment(item.name)
        key = normalize_text(name)
        if name and key not in seen:
            accepted_items.append(item.model_copy(update={"name": name}))
            seen.add(key)

    ignored_fragments = [fragment for fragment in extraction.ignored if clean_fragment(fragment.text)]
    grounding = grounding or GroundingResult()
    return ManualIngredientParseResult(
        accepted=[item.name for item in accepted_items],
        ignored=[fragment.text for fragment in ignored_fragments],
        accepted_items=accepted_items,
        ignored_fragments=ignored_fragments,
        agent_notes=[extraction.reasoning_summary, *extraction.agent_notes],
        used_agent=used_agent,
        search_used=grounding.used,
        search_queries=grounding.search_queries,
    )


def parse_manual_ingredients(text: str, extractor: Extractor | None = None) -> ManualIngredientParseResult:
    """Extract fridge ingredients from natural language using an agentic flow."""
    fragments = split_user_text(text or "")
    if not fragments:
        return ManualIngredientParseResult()

    if extractor:
        extraction = _clean_manual_extraction(extractor(text, fragments))
        return _to_parse_result(extraction, used_agent=True)

    try:
        extraction, grounding = _agentic_extraction(text, fragments)
        return _to_parse_result(extraction, used_agent=True, grounding=grounding)
    except Exception as exc:
        logger.error("No se pudo ejecutar el agente de comprensión manual: %s", exc, exc_info=True)
        extraction = _agent_unavailable_extraction(fragments)
        return _to_parse_result(extraction, used_agent=False)
