from types import SimpleNamespace

from src.fridgechef import persistence


def _settings(**overrides):
    values = {
        "allow_chat_persistence": True,
        "allow_image_storage": True,
        "bucket_name": "demo-bucket",
        "firestore_collection": "demo-sessions",
        "encryption_key": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _FailingFirestore:
    @staticmethod
    def Client():
        raise RuntimeError("cloud is not available")


class _FailingStorage:
    @staticmethod
    def Client():
        raise RuntimeError("cloud is not available")


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
