from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from src.fridgechef.config import get_settings
from src.fridgechef.theme import THEME_CURRENT, theme_options


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LOCK = threading.Lock()
_THEME_PREFERENCE_KEY = "visual_theme"


def _utc_now() -> str:
    """Return one timezone-aware timestamp for preference updates."""
    return datetime.now(timezone.utc).isoformat()


def _database_path() -> Path:
    """Resolve the same SQLite database used by the rest of the application."""
    path = Path(get_settings().local_database_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _owner_id() -> str:
    """Return the application owner used to isolate persisted preferences."""
    return get_settings().inventory_owner_id or "default_user"


def _open_sqlite() -> sqlite3.Connection:
    """Open SQLite and create the shared preference table when it is missing."""
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
    connection.commit()
    return connection


def normalise_visual_theme(value: object) -> str:
    """Return a supported theme key and fall back safely for stale values."""
    selected = str(value or "").strip()
    return selected if selected in theme_options() else THEME_CURRENT


def load_visual_theme_preference() -> str:
    """Load the visual theme from SQLite without breaking application startup."""
    try:
        with _LOCK:
            with _open_sqlite() as connection:
                row = connection.execute(
                    """
                    SELECT preference_value
                    FROM app_preferences
                    WHERE owner_id = ? AND preference_key = ?
                    """,
                    (_owner_id(), _THEME_PREFERENCE_KEY),
                ).fetchone()
        return normalise_visual_theme(row[0]) if row else THEME_CURRENT
    except Exception as exc:
        logger.warning("Could not load visual theme preference: %s", exc)
        return THEME_CURRENT


def save_visual_theme_preference(theme: object) -> str:
    """Persist a validated visual theme and return its canonical key."""
    selected = normalise_visual_theme(theme)
    try:
        with _LOCK:
            with _open_sqlite() as connection:
                connection.execute(
                    """
                    INSERT INTO app_preferences (
                        owner_id,
                        preference_key,
                        preference_value,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(owner_id, preference_key) DO UPDATE SET
                        preference_value = excluded.preference_value,
                        updated_at = excluded.updated_at
                    """,
                    (_owner_id(), _THEME_PREFERENCE_KEY, selected, _utc_now()),
                )
                connection.commit()
    except Exception as exc:
        logger.warning("Could not save visual theme preference: %s", exc)
    return selected
