from __future__ import annotations

import sqlite3

from src.fridgechef import app_preferences
from src.fridgechef.theme import THEME_CURRENT, THEME_DARK, THEME_ELEGANT


def _use_temporary_preferences(monkeypatch, tmp_path, owner_id: str = "test_user"):
    database_path = tmp_path / "fridgechef.db"
    monkeypatch.setattr(app_preferences, "_database_path", lambda: database_path)
    monkeypatch.setattr(app_preferences, "_owner_id", lambda: owner_id)
    return database_path


def test_visual_theme_round_trip_uses_sqlite(monkeypatch, tmp_path):
    database_path = _use_temporary_preferences(monkeypatch, tmp_path)

    assert app_preferences.load_visual_theme_preference() == THEME_CURRENT
    assert app_preferences.save_visual_theme_preference(THEME_DARK) == THEME_DARK
    assert app_preferences.load_visual_theme_preference() == THEME_DARK

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT preference_value
            FROM app_preferences
            WHERE owner_id = ? AND preference_key = ?
            """,
            ("test_user", "visual_theme"),
        ).fetchone()
    assert row == (THEME_DARK,)


def test_visual_theme_update_replaces_the_previous_value(monkeypatch, tmp_path):
    _use_temporary_preferences(monkeypatch, tmp_path)

    app_preferences.save_visual_theme_preference(THEME_DARK)
    app_preferences.save_visual_theme_preference(THEME_ELEGANT)

    assert app_preferences.load_visual_theme_preference() == THEME_ELEGANT


def test_invalid_theme_values_are_normalised_before_storage(monkeypatch, tmp_path):
    _use_temporary_preferences(monkeypatch, tmp_path)

    assert app_preferences.save_visual_theme_preference("unknown-theme") == THEME_CURRENT
    assert app_preferences.load_visual_theme_preference() == THEME_CURRENT


def test_preferences_are_isolated_by_owner(monkeypatch, tmp_path):
    database_path = tmp_path / "fridgechef.db"
    current_owner = {"value": "first_user"}
    monkeypatch.setattr(app_preferences, "_database_path", lambda: database_path)
    monkeypatch.setattr(app_preferences, "_owner_id", lambda: current_owner["value"])

    app_preferences.save_visual_theme_preference(THEME_DARK)
    current_owner["value"] = "second_user"
    app_preferences.save_visual_theme_preference(THEME_ELEGANT)

    assert app_preferences.load_visual_theme_preference() == THEME_ELEGANT
    current_owner["value"] = "first_user"
    assert app_preferences.load_visual_theme_preference() == THEME_DARK


def test_database_failures_do_not_break_application_startup(monkeypatch):
    def fail_to_open():
        raise sqlite3.OperationalError("database unavailable")

    monkeypatch.setattr(app_preferences, "_open_sqlite", fail_to_open)

    assert app_preferences.load_visual_theme_preference() == THEME_CURRENT
    assert app_preferences.save_visual_theme_preference(THEME_DARK) == THEME_DARK
