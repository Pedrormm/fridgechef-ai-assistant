from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.fridgechef.config import get_settings
from src.fridgechef.llm_client import get_client

try:
    from google.genai import types
except Exception:  # pragma: no cover - local environments without google-genai
    types = None

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LOCK = threading.Lock()
_PATCHED_FLAG = "_fridgechef_i18n_installed"
_TRANSLATION_CACHE_VERSION = "20260715_language_quality_v4"

_LANGUAGE_ES = "es"
_LANGUAGE_EN = "en"


@dataclass(frozen=True)
class TranslationAudit:
    """Small audit object returned by the translation guardrail callback."""

    accepted: bool
    text: str
    note: str = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _database_path() -> Path:
    settings = get_settings()
    path = Path(settings.local_database_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _open_sqlite() -> sqlite3.Connection:
    """Open the local app database and create the language tables if needed."""
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS app_preferences (
            owner_id TEXT NOT NULL,
            preference_key TEXT NOT NULL,
            preference_value TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (owner_id, preference_key)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS translation_cache (
            cache_key TEXT PRIMARY KEY,
            source_text TEXT NOT NULL,
            target_language TEXT NOT NULL,
            translated_text TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def _owner_id() -> str:
    return get_settings().inventory_owner_id or "default_user"


def normalise_language(value: object) -> str:
    """Return the only two language codes accepted by the UI."""
    clean = str(value or "").strip().lower()
    return _LANGUAGE_EN if clean.startswith("en") else _LANGUAGE_ES


def load_language_preference() -> str:
    """Load the selected app language from SQLite.

    Language is intentionally stored locally even when inventory persistence is
    disabled. It is a harmless interface preference and should survive browser
    refreshes during local demos.
    """
    try:
        with _LOCK:
            with _open_sqlite() as connection:
                row = connection.execute(
                    """
                    SELECT preference_value
                    FROM app_preferences
                    WHERE owner_id = ? AND preference_key = 'language'
                    """,
                    (_owner_id(),),
                ).fetchone()
        return normalise_language(row[0]) if row else _LANGUAGE_ES
    except Exception as exc:
        logger.warning("Could not load language preference: %s", exc)
        return _LANGUAGE_ES


def save_language_preference(language: object) -> str:
    """Persist the selected language and return the normalised value."""
    selected = normalise_language(language)
    try:
        with _LOCK:
            with _open_sqlite() as connection:
                connection.execute(
                    """
                    INSERT INTO app_preferences (owner_id, preference_key, preference_value, updated_at)
                    VALUES (?, 'language', ?, ?)
                    ON CONFLICT(owner_id, preference_key) DO UPDATE SET
                        preference_value = excluded.preference_value,
                        updated_at = excluded.updated_at
                    """,
                    (_owner_id(), selected, _utc_now()),
                )
                connection.commit()
    except Exception as exc:
        logger.warning("Could not save language preference: %s", exc)
    return selected


def _cache_key(source_text: str, target_language: str) -> str:
    payload = json.dumps(
        {
            "version": _TRANSLATION_CACHE_VERSION,
            "source": source_text,
            "language": target_language,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_cached_translation(source_text: str, target_language: str) -> str | None:
    try:
        key = _cache_key(source_text, target_language)
        with _LOCK:
            with _open_sqlite() as connection:
                row = connection.execute(
                    "SELECT translated_text FROM translation_cache WHERE cache_key = ?",
                    (key,),
                ).fetchone()
        return str(row[0]) if row else None
    except Exception as exc:
        logger.debug("Could not read translation cache: %s", exc)
        return None


def _save_cached_translation(source_text: str, target_language: str, translated_text: str) -> None:
    try:
        key = _cache_key(source_text, target_language)
        with _LOCK:
            with _open_sqlite() as connection:
                connection.execute(
                    """
                    INSERT INTO translation_cache (cache_key, source_text, target_language, translated_text, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        translated_text = excluded.translated_text,
                        updated_at = excluded.updated_at
                    """,
                    (key, source_text, target_language, translated_text, _utc_now()),
                )
                connection.commit()
    except Exception as exc:
        logger.debug("Could not write translation cache: %s", exc)


def _looks_non_linguistic(text: str) -> bool:
    """Avoid wasting model calls on numbers, empty text and pure symbols."""
    clean = (text or "").strip()
    if not clean:
        return True
    if len(clean) <= 2 and not any(ch.isalpha() for ch in clean):
        return True
    if re.fullmatch(r"[\W\d_]+", clean, flags=re.UNICODE):
        return True
    return False


def _strip_model_wrapping(text: str) -> str:
    """Remove accidental quotes or code fences from a translation response."""
    clean = str(text or "").strip()
    clean = clean.replace("```text", "").replace("```", "").strip()
    if len(clean) >= 2 and clean[0] == clean[-1] and clean[0] in {'"', "'"}:
        clean = clean[1:-1].strip()
    return clean


class TranslationAgent:
    """AI translator used for runtime UI copy and model output."""

    def translate(self, source_text: str, target_language: str) -> str:
        if types is None:
            raise RuntimeError("google-genai types are not available")

        settings = get_settings()
        client = get_client()
        target_name = "English from the United States" if target_language == _LANGUAGE_EN else "Spanish from Spain"
        prompt = f"""
You are the translation agent for FridgeChef AI Assistant.

Translate the following application text into {target_name}.
The text belongs to a cooking web app, not to a restaurant menu unless the sentence clearly says so.
Keep the tone natural, friendly and clear for end users.
Translate every food name, ingredient name, UI title, button, status message and recipe sentence that can be translated.
Do not leave Spanish words in English output, except brand names, file names, code-like identifiers, URLs or abbreviations that should remain unchanged.
Important UI terminology for this app:
- "Claro" is the visual theme name and must be translated as "Light" in English.
- "Oscuro" is the visual theme name and must be translated as "Dark" in English.
- "Elegante" is the visual theme name and must be translated as "Elegant" in English.
- "Entrada" is the input section of the app and must be translated as "Input" in English, never as "Appetizer".
- "Tomate frito" is a food ingredient and should be translated as "fried tomato sauce" in English.
- "Estado no confirmado" should read naturally as "Unconfirmed" in English UI cards.
- "Cantidad no indicada" should read naturally as "Quantity not specified" in English UI cards.
- "Escrito manualmente" should read naturally as "Manually entered" in English UI cards.
When translating back to Spanish from English, use natural Spanish from Spain and keep the current Spanish wording style.
Preserve Markdown, headings, bullet markers, emojis, numbers, units, variable-looking tokens, filenames and HTML tag names if any appear.
Do not add explanations, alternatives, notes or quotation marks.
Return only the translated text.

Text:
{source_text}
"""
        response = client.models.generate_content(
            model=settings.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.0),
        )
        return _strip_model_wrapping(response.text or "")


class TranslationGuardrailAgent:
    """Guardrail callback that keeps bad translations out of the UI."""

    def after_translation(self, source_text: str, translated_text: str, target_language: str) -> TranslationAudit:
        clean = _strip_model_wrapping(translated_text)
        if not clean:
            return TranslationAudit(False, source_text, "empty_translation")
        if len(clean) > max(5000, len(source_text) * 8):
            return TranslationAudit(False, source_text, "translation_too_long")
        return TranslationAudit(True, clean)


_TRANSLATOR = TranslationAgent()
_GUARDRAIL = TranslationGuardrailAgent()


def translate_text(value: object, target_language: object = _LANGUAGE_ES) -> str:
    """Translate visible UI/model text with the AI agent and SQLite cache.

    Spanish is the source and default language of the project, so no model call
    is needed when the selected language is Spanish. English uses the translation
    agent once per unique text and then reuses the cached result.
    """
    source_text = str(value or "")
    language = normalise_language(target_language)
    if language == _LANGUAGE_ES or _looks_non_linguistic(source_text):
        return source_text

    cached = _load_cached_translation(source_text, language)
    if cached is not None:
        return cached

    try:
        translated = _TRANSLATOR.translate(source_text, language)
        audit = _GUARDRAIL.after_translation(source_text, translated, language)
        result = audit.text if audit.accepted else source_text
        _save_cached_translation(source_text, language, result)
        return result
    except Exception as exc:
        logger.warning("Translation agent unavailable: %s", exc)
        return source_text


def translate_markdown(value: object, target_language: object = _LANGUAGE_ES) -> str:
    """Translate Markdown-like text while keeping display safe."""
    return translate_text(value, target_language)


def language_option_label(code: str, current_language: str, *, mobile: bool = False) -> str:
    """Format the language selector for desktop and mobile.

    Desktop/tablet keeps the label as plain text to avoid the previous overlap
    caused by graphical flag decorations. Mobile uses native Unicode flag
    characters directly inside the selectbox option text, with no SVG/CSS
    overlays, so the flag is part of the label and cannot float over the text.
    """
    selected = normalise_language(current_language)
    candidate = normalise_language(code)

    if selected == _LANGUAGE_EN:
        label = "Spanish" if candidate == _LANGUAGE_ES else "English"
    else:
        label = "Español" if candidate == _LANGUAGE_ES else "Inglés"

    if not mobile:
        return label

    flag = "🇪🇸" if candidate == _LANGUAGE_ES else "🇺🇸"
    return f"{flag} {label}"

def _translate_call_args(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    language_getter: Callable[[], str],
    *,
    translate_first_arg: bool = True,
    translate_all_args: bool = False,
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Translate common Streamlit label/help/placeholder arguments."""
    if kwargs.pop("__skip_i18n", False):
        return args, kwargs

    language = language_getter()
    new_args = list(args)
    if new_args and translate_first_arg and isinstance(new_args[0], str):
        new_args[0] = translate_text(new_args[0], language)
    if translate_all_args:
        new_args = [translate_text(item, language) if isinstance(item, str) else item for item in new_args]

    new_kwargs = dict(kwargs)
    for key in ("label", "help", "placeholder", "caption"):
        if isinstance(new_kwargs.get(key), str):
            new_kwargs[key] = translate_text(new_kwargs[key], language)

    if callable(new_kwargs.get("format_func")):
        original = new_kwargs["format_func"]

        def translated_format_func(item: Any) -> str:
            return translate_text(original(item), language_getter())

        new_kwargs["format_func"] = translated_format_func
    return tuple(new_args), new_kwargs


def install_streamlit_i18n(streamlit_module: Any, language_getter: Callable[[], str]) -> None:
    """Patch Streamlit display calls so visible text follows the selected language.

    The patch is intentionally conservative: HTML/CSS blocks marked as unsafe are
    not translated because changing them can break layout rules. User-visible
    unsafe HTML is translated explicitly in the app before rendering.
    """
    if getattr(streamlit_module, _PATCHED_FLAG, False):
        return

    def patch(name: str, *, translate_all_args: bool = False, skip_unsafe_html: bool = False) -> None:
        original = getattr(streamlit_module, name, None)
        if original is None:
            return

        def wrapped(*args: Any, **kwargs: Any):
            if skip_unsafe_html and kwargs.get("unsafe_allow_html"):
                return original(*args, **kwargs)
            new_args, new_kwargs = _translate_call_args(
                args,
                kwargs,
                language_getter,
                translate_all_args=translate_all_args,
            )
            return original(*new_args, **new_kwargs)

        setattr(streamlit_module, name, wrapped)

    for method_name in (
        "header",
        "subheader",
        "caption",
        "info",
        "warning",
        "error",
        "success",
        "text_input",
        "text_area",
        "button",
        "toggle",
        "checkbox",
        "radio",
        "selectbox",
        "slider",
        "file_uploader",
        "camera_input",
        "spinner",
        "expander",
        "status",
    ):
        patch(method_name)

    patch("write", translate_all_args=True)
    patch("markdown", skip_unsafe_html=True)

    original_tabs = getattr(streamlit_module, "tabs", None)
    if original_tabs is not None:
        def wrapped_tabs(tabs: Any, *args: Any, **kwargs: Any):
            language = language_getter()
            translated_tabs = [translate_text(item, language) if isinstance(item, str) else item for item in tabs]
            return original_tabs(translated_tabs, *args, **kwargs)

        streamlit_module.tabs = wrapped_tabs

    original_image = getattr(streamlit_module, "image", None)
    if original_image is not None:
        def wrapped_image(*args: Any, **kwargs: Any):
            language = language_getter()
            if isinstance(kwargs.get("caption"), str):
                kwargs = dict(kwargs)
                kwargs["caption"] = translate_text(kwargs["caption"], language)
            return original_image(*args, **kwargs)

        streamlit_module.image = wrapped_image

    setattr(streamlit_module, _PATCHED_FLAG, True)
