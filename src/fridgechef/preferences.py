from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from src.fridgechef.json_utils import extract_json_object
from src.fridgechef.models import UserProfile

try:
    from google.genai import types
except Exception:  # pragma: no cover - optional during local unit tests
    types = None

try:
    from src.fridgechef.config import get_settings
    from src.fridgechef.llm_client import get_client
except Exception:  # pragma: no cover
    get_settings = None
    get_client = None


@dataclass(frozen=True)
class PreferenceValidationIssue:
    """One friendly validation message for a custom preference field."""

    field_label: str
    message: str


_FORBIDDEN_FREE_TEXT_RE = re.compile(r"(https?://|www\.|<script|</|{|}|;\s*drop\s+|select\s+\*)", re.I)


class PreferenceValidationError(ValueError):
    """Raised when a custom user preference is incomplete or not usable."""

    def __init__(self, issues: Iterable[PreferenceValidationIssue]):
        self.issues = list(issues)
        message = "\n".join(issue.message for issue in self.issues)
        super().__init__(message)


def field_label(field: str) -> str:
    """Return the Spanish UI label for a profile field."""
    if field == "diet":
        return "Dieta"
    if field == "allergies":
        return "Alergias"
    if field == "intolerances":
        return "Intolerancias"
    if field == "dislikes":
        return "Alimentos que prefiero evitar"
    if field == "goals":
        return "Objetivo"
    return field


def field_meaning(field: str) -> str:
    """Describe what the custom value should mean without using option lists."""
    if field == "diet":
        return "una dieta, un estilo de alimentación o una restricción general para las recetas"
    if field == "allergies":
        return "una alergia alimentaria que deba evitarse"
    if field == "intolerances":
        return "una intolerancia alimentaria o digestiva"
    if field == "dislikes":
        return "algo relacionado con alimentos, ingredientes, sabores o preparaciones que la persona quiere evitar"
    if field == "goals":
        return "un objetivo relacionado con cocina, alimentación, recetas, nutrición o aprovechamiento de la nevera"
    return "una preferencia relacionada con la alimentación"


def _clean_custom_value(value: str) -> str:
    """Keep custom preference text readable and safe for prompts."""
    return re.sub(r"\s+", " ", (value or "").strip())


def _looks_safe_enough(value: str) -> bool:
    """Reject obviously technical or malicious text before any model call."""
    clean = _clean_custom_value(value)
    if not clean or len(clean) > 100:
        return False
    if _FORBIDDEN_FREE_TEXT_RE.search(clean):
        return False
    return bool(re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", clean))


def _agent_accepts_preference(field: str, value: str) -> bool:
    """Ask a validation agent whether a custom preference is meaningful."""
    if types is None or get_client is None or get_settings is None:
        return True

    try:
        client = get_client()
        settings = get_settings()
        prompt = f"""
Eres el agente de validación de preferencias de FridgeChef AI Assistant.

Tarea:
- Decide si el texto personalizado tiene sentido para el campo indicado.
- Decide por significado y contexto, no mediante listas fijas.
- El texto debe ser útil para analizar alimentos o generar recetas.
- Devuelve solo JSON válido.

Campo: {field_label(field)}
Significado esperado: {field_meaning(field)}
Texto del usuario: {value}

Estructura obligatoria:
{{
  "is_valid": true,
  "reason": "motivo breve en español"
}}
"""
        response = client.models.generate_content(
            model=settings.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json"),
        )
        data = extract_json_object(response.text or "")
        return bool(data.get("is_valid"))
    except Exception:
        return True


def validate_profile_preferences(profile: UserProfile) -> UserProfile:
    """Validate custom selector values before analysis or recipe generation.

    The sidebar allows an "Otra/Otro" option in each preference group. This
    callback makes that flexibility safe: blank values are explained clearly,
    technical snippets are rejected, and meaningful values are appended to the
    normal profile lists before the recipe agents use the profile.
    """
    custom_values = dict(getattr(profile, "custom_preferences", {}) or {})
    issues: list[PreferenceValidationIssue] = []
    updates: dict[str, list[str]] = {}

    for field, raw_value in custom_values.items():
        value = _clean_custom_value(raw_value)
        label = field_label(field)
        if not value:
            issues.append(
                PreferenceValidationIssue(
                    label,
                    f"Has elegido 'Otra/Otro' en {label}, pero no has escrito ninguna información. Añade el detalle o desmarca esa opción.",
                )
            )
            continue
        if not _looks_safe_enough(value) or not _agent_accepts_preference(field, value):
            issues.append(
                PreferenceValidationIssue(
                    label,
                    f"No he podido interpretar correctamente lo escrito en {label}. Escribe una preferencia alimentaria clara y sencilla.",
                )
            )
            continue

        current = list(getattr(profile, field, []) or [])
        if value not in current:
            current.append(value)
        updates[field] = current

    if issues:
        raise PreferenceValidationError(issues)

    return profile.model_copy(update=updates)
