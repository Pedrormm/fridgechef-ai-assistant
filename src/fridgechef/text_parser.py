from __future__ import annotations

import json
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


@dataclass(frozen=True)
class ManualIngredientParseResult:
    """Validated manual input split into food items and rejected text fragments."""

    accepted: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)
    accepted_items: list[IngredientMention] = field(default_factory=list)
    ignored_fragments: list[IgnoredTextFragment] = field(default_factory=list)
    agent_notes: list[str] = field(default_factory=list)
    used_agent: bool = False

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
    """Split free text into short reviewable fragments.

    This step only prepares the text for the language agent. It does not decide
    whether a fragment is food, and it does not rely on food dictionaries.
    """
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
    """Return a safe result when the semantic agent cannot be reached.

    The course requirement forbids replacing semantic understanding with local
    keyword tables. Therefore this fallback does not classify food locally; it
    asks the user to retry when the AI agent is available.
    """
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


def _ground_ambiguous_references(text: str, fragments: list[str]) -> str:
    """Ask a search-enabled sub-agent for context about ambiguous references."""
    try:
        client = get_client()
        settings = get_settings()
        prompt = f"""
Eres el subagente de búsqueda de FridgeChef AI Assistant.

Tarea:
- Revisa el texto del usuario y sus fragmentos.
- Usa Google Search solo si una parte puede referirse a una entidad ambigua, un nombre propio, una marca o una referencia cultural.
- No extraigas ingredientes aquí. Devuelve únicamente notas breves que ayuden a otro agente a decidir si cada fragmento describe un alimento disponible.
- Escribe siempre en español de España.

Texto del usuario:
{text}

Fragmentos:
{json.dumps(fragments, ensure_ascii=False, indent=2)}

Devuelve notas concisas en español, sin información privada.
"""
        response = client.models.generate_content(
            model=settings.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        return response.text or ""
    except Exception:
        return ""


def _agentic_extraction(text: str, fragments: list[str]) -> ManualIngredientExtraction:
    """Run the language-understanding flow for manual fridge text."""
    if types is None:
        raise RuntimeError("google-genai types are not available in this environment.")
    client = get_client()
    settings = get_settings()
    grounding_notes = _ground_ambiguous_references(text, fragments)

    prompt = f"""
Eres el agente de comprensión de texto de FridgeChef AI Assistant.

Objetivo:
Extrae solo alimentos reales que el usuario afirma tener disponibles para cocinar o revisar.

Reglas:
- Comprende lenguaje natural en español o inglés.
- Decide por significado y contexto, no mediante listas fijas de alimentos.
- Conserva cantidades cuando aparezcan.
- Rechaza comentarios, bromas, nombres propios, referencias culturales, objetos que no sean comida y frases ajenas a la nevera.
- Si el texto mezcla alimentos y partes no relacionadas, conserva los alimentos y explica de forma amable lo que se ha ignorado.
- Normaliza el nombre a un ingrediente claro, sin convertirlo en una frase larga.
- Todos los textos visibles deben estar en español de España.
- Devuelve solo JSON válido.

Texto del usuario:
{text}

Fragmentos que debes evaluar:
{json.dumps(fragments, ensure_ascii=False, indent=2)}

Notas del subagente de búsqueda:
{grounding_notes or "Sin notas adicionales."}

Estructura obligatoria:
{{
  "accepted": [
    {{
      "name": "nombre del alimento sin la cantidad",
      "quantity_label": "cantidad en español claro, o Cantidad no indicada",
      "source_text": "fragmento exacto del usuario que originó el alimento",
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
"""
    response = client.models.generate_content(
        model=settings.model_name,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json"),
    )
    data = extract_json_object(response.text)
    extraction = ManualIngredientExtraction.model_validate(data)
    return ensure_manual_extraction_spanish(extraction)


def _to_parse_result(extraction: ManualIngredientExtraction, used_agent: bool) -> ManualIngredientParseResult:
    """Convert the structured agent output into the stable public return type."""
    accepted_items = []
    seen: set[str] = set()
    for item in extraction.accepted:
        name = clean_fragment(item.name)
        key = normalize_text(name)
        if name and key not in seen:
            accepted_items.append(item.model_copy(update={"name": name}))
            seen.add(key)

    ignored_fragments = [fragment for fragment in extraction.ignored if clean_fragment(fragment.text)]
    return ManualIngredientParseResult(
        accepted=[item.name for item in accepted_items],
        ignored=[fragment.text for fragment in ignored_fragments],
        accepted_items=accepted_items,
        ignored_fragments=ignored_fragments,
        agent_notes=[extraction.reasoning_summary, *extraction.agent_notes],
        used_agent=used_agent,
    )


def parse_manual_ingredients(text: str, extractor: Extractor | None = None) -> ManualIngredientParseResult:
    """Extract fridge ingredients from natural language using an agentic flow.

    Tests can inject an extractor so behavior is deterministic without external
    calls. When the agent is unavailable, the function does not emulate semantic
    understanding with local word lists; it returns a safe, friendly message.
    """
    fragments = split_user_text(text or "")
    if not fragments:
        return ManualIngredientParseResult()

    if extractor:
        extraction = ensure_manual_extraction_spanish(extractor(text, fragments))
        return _to_parse_result(extraction, used_agent=True)

    try:
        extraction = _agentic_extraction(text, fragments)
        return _to_parse_result(extraction, used_agent=True)
    except Exception:
        extraction = _agent_unavailable_extraction(fragments)
        return _to_parse_result(extraction, used_agent=False)
