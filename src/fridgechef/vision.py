from __future__ import annotations

import hashlib
import logging
import sqlite3
import threading
from pathlib import Path

from google.genai import types

from src.fridgechef.config import get_settings
from src.fridgechef.json_utils import extract_json_object
from src.fridgechef.llm_client import get_client
from src.fridgechef.models import FridgeAnalysis
from src.fridgechef.security import validate_image_upload
from src.fridgechef.spanish_guard import ensure_fridge_analysis_spanish

VISION_PROMPT = """
Eres el agente visual de FridgeChef AI Assistant.
Analiza una imagen de nevera, despensa, alimento o producto y devuelve solo JSON válido.

Reglas de detección:
- Detecta únicamente elementos visibles y razonablemente claros.
- No inventes alimentos, cantidades, fechas ni marcas.
- Si algo no está claro, colócalo en uncertain_items en lugar de adivinar.
- Si un elemento parece estar en mal estado, marca el estado adecuado y explica la evidencia visual.
- Nunca confirmes seguridad alimentaria solo a partir de una imagen.
- Todos los textos visibles del JSON deben estar en español de España.
- Deja barcode_observations vacío si no se ve ninguna etiqueta, fecha o código legible.

Required JSON shape:
{
  "visible_ingredients": [
    {"name":"string","quantity_estimate":"string or null","state":"fresh|aging|possible_spoiled|unknown","confidence":0.0,"evidence":"string or null"}
  ],
  "possible_spoiled_items": [
    {"name":"string","quantity_estimate":"string or null","state":"possible_spoiled","confidence":0.0,"evidence":"string or null"}
  ],
  "uncertain_items": ["string"],
  "barcode_observations": [
    {"barcode_text":"string or null","expiry_text":"string or null","product_name_guess":"string or null","confidence":0.0,"notes":["string"]}
  ],
  "notes": ["string"]
}
"""

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CACHE_LOCK = threading.Lock()
_LOGGER = logging.getLogger(__name__)


def _database_path(settings) -> Path:
    """Resolve the shared SQLite path used by the production container."""
    path = Path(settings.local_database_path)
    return path if path.is_absolute() else _PROJECT_ROOT / path


def _open_cache(settings) -> sqlite3.Connection:
    """Open the persistent vision cache and create its table when required."""
    path = _database_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS vision_analysis_cache (
            cache_key TEXT PRIMARY KEY,
            analysis_json TEXT NOT NULL,
            model_name TEXT NOT NULL,
            location TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.commit()
    return connection


def _cache_key(image_bytes: bytes, mime_type: str) -> str:
    """Build a stable key from the exact image payload and its declared type."""
    digest = hashlib.sha256()
    digest.update((mime_type or "application/octet-stream").encode("utf-8"))
    digest.update(b"\0")
    digest.update(image_bytes)
    return digest.hexdigest()


def _load_cached_analysis(settings, key: str) -> FridgeAnalysis | None:
    """Return a previous successful analysis without making another model call."""
    try:
        with _CACHE_LOCK:
            with _open_cache(settings) as connection:
                row = connection.execute(
                    "SELECT analysis_json FROM vision_analysis_cache WHERE cache_key = ?",
                    (key,),
                ).fetchone()
        if row:
            return FridgeAnalysis.model_validate_json(str(row[0]))
    except Exception as exc:
        _LOGGER.warning("Vision cache read skipped: %s", _error_summary(exc))
    return None


def _save_cached_analysis(
    settings,
    key: str,
    analysis: FridgeAnalysis,
    model_name: str,
    location: str,
) -> None:
    """Persist only successful analyses; cache failures never break the action."""
    try:
        with _CACHE_LOCK:
            with _open_cache(settings) as connection:
                connection.execute(
                    """
                    INSERT INTO vision_analysis_cache (cache_key, analysis_json, model_name, location)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        analysis_json = excluded.analysis_json,
                        model_name = excluded.model_name,
                        location = excluded.location,
                        created_at = CURRENT_TIMESTAMP
                    """,
                    (key, analysis.model_dump_json(), model_name, location),
                )
                connection.commit()
    except Exception as exc:
        _LOGGER.warning("Vision cache write skipped: %s", _error_summary(exc))


def _candidate_models(settings) -> list[str]:
    """Return the configured vision model followed by safe text/vision fallbacks."""
    configured = [settings.model_name]
    configured.extend(
        part.strip()
        for part in str(getattr(settings, "text_fallback_models", "")).split(",")
        if part.strip()
    )
    result: list[str] = []
    for model_name in configured:
        if model_name and model_name not in result:
            result.append(model_name)
    return result


def _candidate_locations(settings) -> list[str]:
    """Prefer Google's global endpoint and retain one regional recovery path."""
    result: list[str] = []
    for location in (getattr(settings, "location", "global"), "global", "us-central1"):
        clean = str(location or "").strip()
        if clean and clean not in result:
            result.append(clean)
    return result


def _error_summary(exc: Exception, limit: int = 260) -> str:
    """Keep cloud errors useful in logs without printing full response payloads."""
    message = " ".join(str(exc).split())
    return f"{type(exc).__name__}: {message[:limit]}"


def _generate_analysis(
    image_bytes: bytes,
    mime_type: str,
    model_name: str,
    location: str,
) -> FridgeAnalysis:
    """Run one structured vision request through the retry-enabled Gen AI client."""
    client = get_client(location=location)
    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    response = client.models.generate_content(
        model=model_name,
        contents=[VISION_PROMPT, image_part],
        config=types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
        ),
    )
    data = extract_json_object(response.text)
    return ensure_fridge_analysis_spanish(FridgeAnalysis.model_validate(data))


def analyze_image_bytes(image_bytes: bytes, mime_type: str) -> FridgeAnalysis:
    """Analyze one image with retries, endpoint/model fallback and SQLite caching."""
    settings = get_settings()
    validate_image_upload(image_bytes, mime_type, settings.max_image_mb)

    key = _cache_key(image_bytes, mime_type)
    cached = _load_cached_analysis(settings, key)
    if cached is not None:
        return cached

    errors: list[str] = []
    for model_name in _candidate_models(settings):
        for location in _candidate_locations(settings):
            try:
                analysis = _generate_analysis(
                    image_bytes,
                    mime_type,
                    model_name,
                    location,
                )
                _save_cached_analysis(settings, key, analysis, model_name, location)
                return analysis
            except Exception as exc:
                summary = _error_summary(exc)
                errors.append(f"{model_name}@{location}: {summary}")
                _LOGGER.warning("Vision attempt failed for %s@%s: %s", model_name, location, summary)

    raise RuntimeError(
        "No configured vision model completed the image analysis. "
        + " | ".join(errors[-4:])
    )
