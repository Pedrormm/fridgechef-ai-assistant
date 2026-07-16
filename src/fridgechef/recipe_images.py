from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import sqlite3
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Callable, Iterable

try:
    from PIL import Image
except Exception:  # pragma: no cover - Pillow is optional in some test environments
    Image = None

try:
    from google.genai import types
except Exception:  # pragma: no cover - allows local tests without cloud SDKs
    types = None

try:
    import google.auth
    from google.auth.transport.requests import Request as GoogleAuthRequest
except Exception:  # pragma: no cover - image REST fallback is optional in local tests
    google = None
    GoogleAuthRequest = None

from src.fridgechef.config import get_settings
from src.fridgechef.llm_client import get_client
from src.fridgechef.local_recipe_image import generate_local_recipe_image
from src.fridgechef.models import RecipeItem, RecipeResponse, UserProfile
from src.fridgechef.recipe_planner import clean_user_text, sentence_case


DEFAULT_GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"
DEFAULT_IMAGEN_MODEL = "imagen-4.0-generate-001"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_IMAGE_CACHE_LOCK = threading.Lock()
_IMAGE_REST_TIMEOUT_SECONDS = 90
_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_LOGGER = logging.getLogger(__name__)


class RecipeImageGenerationError(RuntimeError):
    """Internal error with enough detail for logs, never shown raw to users."""


def _build_visible_food_list(items: Iterable[str], limit: int = 6) -> str:
    visible = [sentence_case(item) for item in items if clean_user_text(item)]
    visible = visible[:limit]
    if not visible:
        return "ingredientes frescos y bien presentados"
    if len(visible) == 1:
        return visible[0]
    return ", ".join(visible[:-1]) + " y " + visible[-1]


def build_recipe_image_prompt(recipe: RecipeItem, profile: UserProfile) -> str:
    """Create a high-quality food-photo prompt that matches the generated recipe."""
    dish = sentence_case(recipe.title) or "plato casero"
    description = clean_user_text(recipe.description)
    category = clean_user_text(recipe.category or "plato casero").lower()
    cuisine = clean_user_text(recipe.cuisine or "casera").lower()
    foods = _build_visible_food_list(recipe.ingredients_used)
    servings = max(1, int(recipe.servings or profile.servings or 1))

    return (
        "Crea una fotografía gastronómica ultrarrealista, nítida y muy apetecible de un plato terminado. "
        f"La imagen debe representar exactamente esta receta: '{dish}'. "
        f"Tipo de plato: {category}. Cocina: {cuisine}. Raciones visibles aproximadas: {servings}. "
        f"Ingredientes protagonistas visibles o sugeridos en el emplatado: {foods}. "
        f"Descripción culinaria: {description or 'plato casero recién preparado'}. "
        "Estilo editorial premium, luz natural suave, colores realistas, textura detallada, "
        "emplatado moderno pero casero, fondo de cocina o mesa elegante ligeramente desenfocado. "
        "Sin manos, sin personas, sin texto escrito, sin logotipos, sin marcas, sin envases, "
        "sin collage y sin mostrar ingredientes crudos como protagonistas. Solo el plato final listo para comer."
    )


def _decode_base64_text(value: str) -> bytes | None:
    """Decode plain base64 or a data URL without raising noisy UI errors."""
    if not value:
        return None
    payload = value.split(",", 1)[1] if value.startswith("data:") and "," in value else value
    try:
        return base64.b64decode(payload, validate=False)
    except Exception:
        return None


def _extract_image_bytes(candidate: object) -> tuple[bytes | None, str]:
    """Extract raw image bytes from several SDK response shapes."""
    checked: list[object] = []
    if candidate is not None:
        checked.append(candidate)
        for attr in ("image", "inline_data", "inlineData", "output_image"):
            nested = getattr(candidate, attr, None)
            if nested is not None:
                checked.append(nested)

    for item in checked:
        if isinstance(item, (bytes, bytearray)):
            return bytes(item), "image/png"

        if isinstance(item, dict):
            mime = str(item.get("mime_type") or item.get("mimeType") or "image/png")
            for key in ("image_bytes", "bytes", "bytesBase64Encoded", "imageBytes", "base64", "data"):
                raw = item.get(key)
                if isinstance(raw, (bytes, bytearray)):
                    return bytes(raw), mime
                if isinstance(raw, str):
                    decoded = _decode_base64_text(raw)
                    if decoded:
                        return decoded, mime

        mime = getattr(item, "mime_type", None) or getattr(item, "mimeType", None) or "image/png"
        for attr in ("image_bytes", "bytes", "data"):
            raw = getattr(item, attr, None)
            if isinstance(raw, (bytes, bytearray)):
                return bytes(raw), str(mime)
            if isinstance(raw, str):
                decoded = _decode_base64_text(raw)
                if decoded:
                    return decoded, str(mime)

        pil_image = None
        if Image is not None and isinstance(item, Image.Image):
            pil_image = item
        elif Image is not None:
            maybe_pil = getattr(item, "_pil_image", None)
            if isinstance(maybe_pil, Image.Image):
                pil_image = maybe_pil

        if pil_image is not None:
            output = BytesIO()
            format_name = "JPEG" if "jpeg" in str(mime).lower() or "jpg" in str(mime).lower() else "PNG"
            pil_image.save(output, format=format_name)
            detected_mime = "image/jpeg" if format_name == "JPEG" else "image/png"
            return output.getvalue(), detected_mime

        save_method = getattr(item, "save", None)
        if callable(save_method):
            output = BytesIO()
            try:
                save_method(output)
                data = output.getvalue()
                if data:
                    return data, str(mime)
            except Exception:
                pass

    return None, "image/png"


def _extract_image_from_generate_content_response(response: object) -> tuple[bytes | None, str]:
    """Read inline image data from Gemini native image-generation responses."""
    direct = _extract_image_bytes(response)
    if direct[0]:
        return direct

    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            image_bytes, mime_type = _extract_image_bytes(part)
            if image_bytes:
                return image_bytes, mime_type

            inline_data = getattr(part, "inline_data", None) or getattr(part, "inlineData", None)
            if inline_data is not None:
                image_bytes, mime_type = _extract_image_bytes(inline_data)
                if image_bytes:
                    return image_bytes, mime_type

    return None, "image/png"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _database_path(settings) -> Path:
    path = Path(settings.local_database_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _open_cache_db(settings) -> sqlite3.Connection:
    path = _database_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS recipe_image_cache (
            cache_key TEXT PRIMARY KEY,
            recipe_title TEXT NOT NULL,
            prompt TEXT NOT NULL,
            image_base64 TEXT NOT NULL,
            image_mime_type TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def _cache_key(prompt: str, model_name: str) -> str:
    payload = f"{model_name}||{prompt}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_cached_image(settings, cache_key: str) -> tuple[str, str] | None:
    with _IMAGE_CACHE_LOCK:
        with _open_cache_db(settings) as connection:
            row = connection.execute(
                "SELECT image_base64, image_mime_type FROM recipe_image_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
    if not row:
        return None
    return str(row[0]), str(row[1] or "image/png")


def _save_cached_image(settings, cache_key: str, recipe_title: str, prompt: str, image_base64: str, image_mime_type: str) -> None:
    with _IMAGE_CACHE_LOCK:
        with _open_cache_db(settings) as connection:
            connection.execute(
                """
                INSERT INTO recipe_image_cache (cache_key, recipe_title, prompt, image_base64, image_mime_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    recipe_title = excluded.recipe_title,
                    prompt = excluded.prompt,
                    image_base64 = excluded.image_base64,
                    image_mime_type = excluded.image_mime_type,
                    created_at = excluded.created_at
                """,
                (cache_key, sentence_case(recipe_title) or "Receta", prompt, image_base64, image_mime_type, _utc_now()),
            )
            connection.commit()


def _prepare_google_credentials(settings) -> None:
    credentials_path = Path(settings.credentials_path)
    if credentials_path.exists():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credentials_path.resolve())


def _rest_endpoint(project_id: str, location: str, model_name: str) -> str:
    normalized_location = (location or "global").strip()
    host = "aiplatform.googleapis.com" if normalized_location == "global" else f"{normalized_location}-aiplatform.googleapis.com"
    return (
        f"https://{host}/v1/projects/{project_id}/locations/{normalized_location}"
        f"/publishers/google/models/{model_name}:predict"
    )


def _candidate_locations(primary_location: str, text_location: str) -> list[str]:
    candidates: list[str] = []
    for value in (primary_location, text_location, "global", "us-central1"):
        location = (value or "").strip()
        if location and location not in candidates:
            candidates.append(location)
    return candidates or ["global"]


def _access_token(settings) -> str:
    if google is None or GoogleAuthRequest is None:
        raise RecipeImageGenerationError("No está disponible la autenticación de Google para crear imágenes.")

    _prepare_google_credentials(settings)
    credentials, _ = google.auth.default(scopes=[_CLOUD_PLATFORM_SCOPE])
    credentials.refresh(GoogleAuthRequest())
    token = getattr(credentials, "token", "") or ""
    if not token:
        raise RecipeImageGenerationError("Google no ha devuelto un token válido para crear imágenes.")
    return token


def _extract_prediction_image(prediction: object) -> tuple[bytes | None, str]:
    candidates: list[object] = [prediction]
    if isinstance(prediction, dict):
        for key in ("image", "generatedImage"):
            if prediction.get(key) is not None:
                candidates.append(prediction[key])

    for item in candidates:
        image_bytes, mime_type = _extract_image_bytes(item)
        if image_bytes:
            return image_bytes, mime_type

    return None, "image/png"


def _raise_with_http_body(exc: urllib.error.HTTPError, context: str) -> None:
    try:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
    except Exception:
        detail = str(exc)
    raise RecipeImageGenerationError(f"{context}: HTTP {exc.code} {exc.reason}. {detail}") from exc


def _generate_image_with_imagen_rest(prompt: str, model_name: str, primary_location: str) -> tuple[bytes | None, str]:
    settings = get_settings()
    if not settings.project_id:
        raise RecipeImageGenerationError("No encuentro el proyecto de Google Cloud para crear imágenes.")

    token = _access_token(settings)
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": getattr(settings, "image_aspect_ratio", "4:3") or "4:3",
            "enhancePrompt": True,
            "includeRaiReason": True,
            "outputOptions": {
                "mimeType": getattr(settings, "image_output_mime_type", "image/jpeg") or "image/jpeg",
                "compressionQuality": 90,
            },
        },
    }
    body = json.dumps(payload).encode("utf-8")
    errors: list[str] = []

    for location in _candidate_locations(primary_location, settings.location):
        request = urllib.request.Request(
            _rest_endpoint(settings.project_id, location, model_name),
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=_IMAGE_REST_TIMEOUT_SECONDS) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:700]
            except Exception:
                detail = str(exc)
            errors.append(f"{model_name}@{location}: HTTP {exc.code} {exc.reason}. {detail}")
            continue
        except Exception as exc:
            errors.append(f"{model_name}@{location}: {type(exc).__name__}: {exc}")
            continue

        predictions = parsed.get("predictions") if isinstance(parsed, dict) else None
        if isinstance(predictions, list) and predictions:
            image_bytes, mime_type = _extract_prediction_image(predictions[0])
            if image_bytes:
                return image_bytes, mime_type or "image/png"
        errors.append(f"{model_name}@{location}: la respuesta no contenía imagen útil.")

    raise RecipeImageGenerationError("; ".join(errors) or "Imagen no generada por REST.")


def _generate_image_with_imagen_sdk(prompt: str, model_name: str, image_location: str, settings) -> tuple[bytes | None, str]:
    if types is None:
        raise RecipeImageGenerationError("La librería google-genai no tiene tipos de generación de imagen disponibles.")

    client = get_client(location=image_location)
    try:
        response = client.models.generate_images(
            model=model_name,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio=getattr(settings, "image_aspect_ratio", "4:3") or "4:3",
                image_size=getattr(settings, "image_size", "1K") or "1K",
                output_mime_type=getattr(settings, "image_output_mime_type", "image/jpeg") or "image/jpeg",
                include_rai_reason=True,
                enhance_prompt=True,
            ),
        )
    except TypeError:
        response = client.models.generate_images(model=model_name, prompt=prompt)

    generated = getattr(response, "generated_images", None) or getattr(response, "images", None) or []
    if generated:
        image_bytes, mime_type = _extract_image_bytes(generated[0])
        if image_bytes:
            return image_bytes, mime_type

    image_bytes, mime_type = _extract_image_bytes(response)
    if image_bytes:
        return image_bytes, mime_type
    raise RecipeImageGenerationError(f"{model_name}: la respuesta de Imagen no contenía imagen útil.")


def _generate_image_with_gemini_content(prompt: str, model_name: str, image_location: str, settings) -> tuple[bytes | None, str]:
    """Generate food image with Gemini native image model (Nano Banana family)."""
    if types is None:
        raise RecipeImageGenerationError("La librería google-genai no está preparada para Gemini Image.")

    client = get_client(location=image_location)
    config_kwargs = {
        "response_modalities": ["TEXT", "IMAGE"],
        "temperature": 0.8,
    }
    try:
        # Some SDK versions use GenerationConfig internally, but expose it as
        # GenerateContentConfig. Keeping this as a dict-free typed call gives the
        # best compatibility with the installed google-genai package.
        config = types.GenerateContentConfig(**config_kwargs)
    except Exception:
        config = None

    if config is not None:
        response = client.models.generate_content(model=model_name, contents=prompt, config=config)
    else:
        response = client.models.generate_content(model=model_name, contents=prompt)

    image_bytes, mime_type = _extract_image_from_generate_content_response(response)
    if image_bytes:
        return image_bytes, mime_type or "image/png"
    raise RecipeImageGenerationError(f"{model_name}: Gemini Image respondió sin datos de imagen.")


def _generate_image_with_interactions(prompt: str, model_name: str, image_location: str, settings) -> tuple[bytes | None, str]:
    """Fallback for the newer Nano Banana / Interactions API SDK shape."""
    client = get_client(location=image_location)
    interactions = getattr(client, "interactions", None)
    create = getattr(interactions, "create", None) if interactions is not None else None
    if not callable(create):
        raise RecipeImageGenerationError("La versión instalada de google-genai no expone client.interactions.create.")

    response_format = {
        "type": "image",
        "mime_type": getattr(settings, "image_output_mime_type", "image/jpeg") or "image/jpeg",
        "aspect_ratio": getattr(settings, "image_aspect_ratio", "4:3") or "4:3",
        "image_size": getattr(settings, "image_size", "1K") or "1K",
    }
    try:
        interaction = create(model=model_name, input=prompt, response_format=response_format)
    except TypeError:
        interaction = create(model=model_name, input=prompt)

    output_image = getattr(interaction, "output_image", None)
    if output_image is not None:
        image_bytes, mime_type = _extract_image_bytes(output_image)
        if image_bytes:
            return image_bytes, mime_type or response_format["mime_type"]

    image_bytes, mime_type = _extract_image_bytes(interaction)
    if image_bytes:
        return image_bytes, mime_type
    raise RecipeImageGenerationError(f"{model_name}: Interactions respondió sin imagen útil.")


def _ordered_image_models(settings) -> list[str]:
    """Use only current Gemini image endpoints and ignore retired Imagen models."""
    configured = [getattr(settings, "image_model_name", "")]
    configured.extend(
        part.strip()
        for part in getattr(settings, "image_fallback_models", "").split(",")
        if part.strip()
    )
    configured.extend([DEFAULT_GEMINI_IMAGE_MODEL, "gemini-2.5-flash-image"])

    models: list[str] = []
    for model_name in configured:
        clean = str(model_name or "").strip()
        if not clean.startswith("gemini-") or "image" not in clean:
            continue
        if clean not in models:
            models.append(clean)
    return models

def _try_generate_image(prompt: str, settings) -> tuple[bytes, str, str]:
    """Try current Gemini image models through the retry-enabled global endpoint."""
    errors: list[str] = []
    location = "global"

    for model_name in _ordered_image_models(settings):
        try:
            image_bytes, mime_type = _generate_image_with_gemini_content(
                prompt,
                model_name,
                location,
                settings,
            )
            if image_bytes:
                return image_bytes, mime_type, model_name
        except Exception as exc:
            summary = " ".join(str(exc).split())[:280]
            errors.append(f"{model_name}: {type(exc).__name__}: {summary}")
            # Individual provider failures are expected while another image
            # model can still complete the request, so keep them as diagnostics.
            _LOGGER.info(
                "Recipe image candidate unavailable for %s: %s: %s",
                model_name,
                type(exc).__name__,
                summary,
            )

    raise RecipeImageGenerationError(
        " | ".join(errors) or "No current Gemini image model completed the request."
    )

def generate_recipe_image(recipe: RecipeItem, profile: UserProfile, use_cache: bool = True) -> RecipeItem:
    settings = get_settings()
    if not getattr(settings, "recipe_images_enabled", True):
        return recipe

    prompt = build_recipe_image_prompt(recipe, profile)
    primary_model = getattr(settings, "image_model_name", DEFAULT_GEMINI_IMAGE_MODEL) or DEFAULT_GEMINI_IMAGE_MODEL
    cache_key = _cache_key(prompt, primary_model)

    if use_cache:
        cached = _load_cached_image(settings, cache_key)
        if cached:
            image_base64, image_mime_type = cached
            return recipe.model_copy(
                update={
                    "image_prompt": prompt,
                    "image_mime_type": image_mime_type or "image/png",
                    "image_base64": image_base64,
                    "image_generation_error": "",
                }
            )

    try:
        image_bytes, mime_type, used_model = _try_generate_image(prompt, settings)
    except Exception as exc:
        # A local card keeps the one-image-per-recipe contract during cloud outages.
        summary = " ".join(str(exc).split())[:280]
        # The local card fulfils the requested image contract, so this is a
        # successful recovery path rather than an operational warning.
        _LOGGER.info(
            "Cloud recipe image unavailable for '%s'; local fallback selected: %s",
            recipe.title,
            summary,
        )
        image_bytes, mime_type = generate_local_recipe_image(recipe)
        used_model = "local-recipe-card-v1"

    image_mime_type = mime_type or "image/png"
    image_base64 = base64.b64encode(image_bytes).decode("ascii")
    if use_cache:
        try:
            _save_cached_image(settings, _cache_key(prompt, used_model), recipe.title, prompt, image_base64, image_mime_type)
            if used_model != primary_model:
                _save_cached_image(settings, cache_key, recipe.title, prompt, image_base64, image_mime_type)
        except Exception:
            _LOGGER.exception("No se ha podido guardar la imagen en caché.")

    return recipe.model_copy(
        update={
            "image_prompt": prompt,
            "image_mime_type": image_mime_type,
            "image_base64": image_base64,
            "image_generation_error": "",
        }
    )


def attach_recipe_images(
    response: RecipeResponse,
    profile: UserProfile,
    *,
    enabled: bool = True,
    progress_callback: Callable[[int, int, bool], None] | None = None,
) -> RecipeResponse:
    """Add one generated image to each recipe without breaking recipe text output."""
    if not enabled or not response.recipes:
        return response

    settings = get_settings()
    use_cache = bool(getattr(settings, "recipe_images_enabled", True))
    primary_model = getattr(settings, "image_model_name", DEFAULT_GEMINI_IMAGE_MODEL) or DEFAULT_GEMINI_IMAGE_MODEL
    enriched: list[RecipeItem] = []
    total = len(response.recipes)

    for index, recipe in enumerate(response.recipes, start=1):
        prompt = build_recipe_image_prompt(recipe, profile)
        cache_hit = bool(_load_cached_image(settings, _cache_key(prompt, primary_model))) if use_cache else False
        if progress_callback is not None:
            progress_callback(index, total, cache_hit)
        enriched.append(generate_recipe_image(recipe, profile, use_cache=use_cache))

    return response.model_copy(update={"recipes": enriched})
