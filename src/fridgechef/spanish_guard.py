from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, TypeVar

try:
    from google.genai import types
except Exception:  # pragma: no cover - optional during local unit tests
    types = None

from pydantic import BaseModel

from src.fridgechef.json_utils import extract_json_object
from src.fridgechef.models import (
    FridgeAnalysis,
    FridgeQuestionDecision,
    ManualIngredientExtraction,
    RecipeReadinessAssessment,
    RecipeResponse,
)

try:
    from src.fridgechef.config import get_settings
    from src.fridgechef.llm_client import get_client
except Exception:  # pragma: no cover - keeps isolated tests importable
    get_settings = None
    get_client = None

T = TypeVar("T", bound=BaseModel)
SpanishPayloadAgent = Callable[[dict[str, Any], str], dict[str, Any]]
SpanishTextAgent = Callable[[str, str], str]

_TAG_RE = re.compile(r"<[^>]*>")
_SPACE_RE = re.compile(r"\s+")


class SpanishGuardError(RuntimeError):
    """Raised when the Spanish guardrail cannot return a usable payload."""


def strip_markup(value: str) -> str:
    """Remove markup that should never be rendered in the user interface."""
    clean = _TAG_RE.sub(" ", value or "")
    return _SPACE_RE.sub(" ", clean).strip()


def _clean_text_value(value: str) -> str:
    """Keep a value display-safe without making language decisions locally."""
    return strip_markup(value).replace("`", "").strip()


def _clean_payload_locally(payload: Any) -> Any:
    """Last-resort cleanup used only when the language agent is unavailable.

    This function deliberately does not translate and does not use keyword lists.
    It only removes markup/control artefacts so no HTML or code leaks into the UI.
    The language correction itself is handled by the Gemini guardrail agent.
    """
    if isinstance(payload, str):
        return _clean_text_value(payload)
    if isinstance(payload, list):
        return [_clean_payload_locally(item) for item in payload]
    if isinstance(payload, dict):
        return {key: _clean_payload_locally(value) for key, value in payload.items()}
    return payload


def _run_spanish_payload_agent(payload: dict[str, Any], context: str) -> dict[str, Any]:
    """Ask Gemini to rewrite every user-visible string in a JSON payload."""
    if types is None or get_client is None or get_settings is None:
        raise SpanishGuardError("El agente de revisión en español no está disponible.")

    client = get_client()
    settings = get_settings()
    prompt = f"""
Eres el agente de revisión lingüística de FridgeChef AI Assistant.

Objetivo:
- Revisa el JSON recibido y devuelve el mismo JSON, con la misma estructura.
- Reescribe todos los textos visibles para el usuario en español de España.
- Corrige gramática, ortografía, acentos y naturalidad.
- No añadas alimentos, cantidades, recetas, fechas ni datos que no estén en la entrada.
- No traduzcas nombres de claves, estados internos, números, booleanos ni valores nulos.
- No devuelvas HTML, Markdown, bloques de código ni explicaciones fuera del JSON.

Contexto de uso:
{context}

JSON que debes revisar:
{json.dumps(payload, ensure_ascii=False, indent=2)}

Devuelve únicamente un objeto JSON válido.
"""
    response = client.models.generate_content(
        model=settings.model_name,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json"),
    )
    result = extract_json_object(response.text or "")
    if not isinstance(result, dict):
        raise SpanishGuardError("El agente de revisión no devolvió un objeto JSON.")
    return result


def _run_spanish_text_agent(text: str, context: str) -> str:
    """Ask Gemini to rewrite one user-visible text fragment in Spanish."""
    if types is None or get_client is None or get_settings is None:
        raise SpanishGuardError("El agente de revisión en español no está disponible.")

    client = get_client()
    settings = get_settings()
    prompt = f"""
Eres el agente de revisión lingüística de FridgeChef AI Assistant.

Reescribe el siguiente texto para que sea español de España, claro, natural y apto para mostrarse en una aplicación web.
Mantén el significado. No añadas datos. No uses HTML, Markdown ni código.

Contexto:
{context}

Texto:
{text}

Devuelve solo el texto final.
"""
    response = client.models.generate_content(
        model=settings.model_name,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0),
    )
    return _clean_text_value(response.text or "")


def ensure_spanish_payload(payload: dict[str, Any], context: str, agent: SpanishPayloadAgent | None = None) -> dict[str, Any]:
    """Return a display-safe payload reviewed by the Spanish guardrail agent."""
    cleaned = _clean_payload_locally(payload)
    try:
        reviewed = agent(cleaned, context) if agent else _run_spanish_payload_agent(cleaned, context)
        return _clean_payload_locally(reviewed)
    except Exception:
        return cleaned


def ensure_spanish_text(text: str, context: str = "", agent: SpanishTextAgent | None = None) -> str:
    """Return one display-safe text reviewed by the Spanish guardrail agent."""
    cleaned = _clean_text_value(text)
    if not cleaned:
        return ""
    try:
        return _clean_text_value(agent(cleaned, context) if agent else _run_spanish_text_agent(cleaned, context))
    except Exception:
        return cleaned


def _ensure_model_payload(model: T, context: str, agent: SpanishPayloadAgent | None = None) -> T:
    """Review a Pydantic model payload and validate it back into the same type."""
    reviewed = ensure_spanish_payload(model.model_dump(), context=context, agent=agent)
    return type(model).model_validate(reviewed)


def ensure_fridge_analysis_spanish(
    analysis: FridgeAnalysis,
    agent: SpanishPayloadAgent | None = None,
) -> FridgeAnalysis:
    """Review all user-visible text produced by the vision agent."""
    return _ensure_model_payload(analysis, "Resultado del análisis visual de alimentos.", agent)


def ensure_manual_extraction_spanish(
    extraction: ManualIngredientExtraction,
    agent: SpanishPayloadAgent | None = None,
) -> ManualIngredientExtraction:
    """Review all user-visible text produced by the manual-input agent."""
    return _ensure_model_payload(extraction, "Resultado de extracción de alimentos desde texto libre.", agent)


def ensure_readiness_spanish(
    assessment: RecipeReadinessAssessment,
    agent: SpanishPayloadAgent | None = None,
) -> RecipeReadinessAssessment:
    """Review all user-visible text produced by the recipe-readiness agent."""
    return _ensure_model_payload(assessment, "Decisión previa a generar recetas.", agent)


def ensure_fridge_question_spanish(
    decision: FridgeQuestionDecision,
    agent: SpanishPayloadAgent | None = None,
) -> FridgeQuestionDecision:
    """Review the answer returned by the fridge-question agent."""
    return _ensure_model_payload(decision, "Respuesta a una pregunta sobre la nevera guardada.", agent)


def ensure_recipe_response_spanish(
    response: RecipeResponse,
    agent: SpanishPayloadAgent | None = None,
) -> RecipeResponse:
    """Review every recipe field before it is rendered."""
    return _ensure_model_payload(response, "Recetas y mensajes mostrados al usuario final.", agent)
