from types import SimpleNamespace

from src.fridgechef import persistence


def _settings(**overrides):
    values = {
        "allow_chat_persistence": True,
        "allow_image_storage": True,
        "bucket_name": "demo-bucket",
        "firestore_collection": "demo-sessions",
        "firestore_inventory_collection": "demo-inventories",
        "firestore_inventory_document": "primary",
        "firestore_database": "(default)",
        "encryption_key": "",
        "credentials_path": "missing-credentials.json",
        "project_id": "demo-project",
        "persistence_backend": "auto",
        "local_database_path": "data/test.db",
        "inventory_owner_id": "test-user",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _FailingFirestore:
    @staticmethod
    def Client(*args, **kwargs):
        raise RuntimeError("cloud is not available")


class _FailingStorage:
    @staticmethod
    def Client(*args, **kwargs):
        raise RuntimeError("cloud is not available")


def test_inventory_roundtrip_uses_sqlite_without_gcloud(monkeypatch, tmp_path):
    settings = _settings(
        persistence_backend="sqlite",
        local_database_path=str(tmp_path / "fridgechef.db"),
    )
    monkeypatch.setattr(persistence, "get_settings", lambda: settings)

    inventory = [{"name": "huevos", "quantity_label": "6 unidades"}]
    saved = persistence.save_inventory_state(inventory)
    loaded = persistence.load_inventory_state()

    assert saved.success is True
    assert saved.backend == "sqlite"
    assert loaded.inventory == inventory


def test_inventory_clear_is_durable(monkeypatch, tmp_path):
    settings = _settings(
        persistence_backend="sqlite",
        local_database_path=str(tmp_path / "fridgechef.db"),
    )
    monkeypatch.setattr(persistence, "get_settings", lambda: settings)

    persistence.save_inventory_state([{"name": "leche"}])
    cleared = persistence.clear_inventory_state()
    loaded = persistence.load_inventory_state()

    assert cleared.success is True
    assert loaded.inventory == []


def test_auto_mode_falls_back_to_sqlite_when_firestore_fails(monkeypatch, tmp_path):
    settings = _settings(
        persistence_backend="auto",
        local_database_path=str(tmp_path / "fridgechef.db"),
    )
    monkeypatch.setattr(persistence, "get_settings", lambda: settings)
    monkeypatch.setattr(persistence, "firestore", _FailingFirestore)

    result = persistence.save_inventory_state([{"name": "tomate"}])

    assert result.success is True
    assert result.backend == "sqlite"
    assert persistence.load_inventory_state().inventory == [{"name": "tomate"}]


def test_session_persistence_is_best_effort(monkeypatch):
    """A cloud write problem must not break the web analysis flow."""
    monkeypatch.setattr(persistence, "get_settings", lambda: _settings())
    monkeypatch.setattr(persistence, "firestore", _FailingFirestore)

    assert persistence.save_session_if_allowed({"event": "inventory_update"}, allow_save=True) is None


def test_image_persistence_is_best_effort(monkeypatch):
    """A cloud upload problem must not prevent local image analysis."""
    monkeypatch.setattr(persistence, "get_settings", lambda: _settings())
    monkeypatch.setattr(persistence, "storage", _FailingStorage)

    assert persistence.save_image_if_allowed(b"image", "image/jpeg", allow_save=True) is None
