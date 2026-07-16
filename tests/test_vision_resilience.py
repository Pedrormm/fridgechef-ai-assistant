from types import SimpleNamespace

from src.fridgechef import vision
from src.fridgechef.models import DetectedIngredient, FridgeAnalysis


def _settings(tmp_path):
    return SimpleNamespace(
        local_database_path=str(tmp_path / "fridgechef.db"),
        max_image_mb=10,
        model_name="primary-vision-model",
        text_fallback_models="fallback-vision-model",
        location="global",
    )


def test_vision_uses_model_fallback_and_caches_success(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    calls: list[tuple[str, str]] = []
    expected = FridgeAnalysis(
        visible_ingredients=[
            DetectedIngredient(
                name="patatas",
                quantity_estimate="4 unidades",
                state="fresh",
                confidence=0.9,
            )
        ]
    )

    monkeypatch.setattr(vision, "get_settings", lambda: settings)
    monkeypatch.setattr(vision, "validate_image_upload", lambda *_args, **_kwargs: None)

    def fake_generate(_image_bytes, _mime_type, model_name, location):
        calls.append((model_name, location))
        if model_name == "primary-vision-model":
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return expected

    monkeypatch.setattr(vision, "_generate_analysis", fake_generate)

    first = vision.analyze_image_bytes(b"same-photo", "image/jpeg")
    first_call_count = len(calls)
    second = vision.analyze_image_bytes(b"same-photo", "image/jpeg")

    assert first == expected
    assert second == expected
    assert first_call_count >= 2
    assert len(calls) == first_call_count
    assert any(model == "fallback-vision-model" for model, _ in calls)


def test_cache_failure_does_not_hide_a_successful_analysis(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    expected = FridgeAnalysis(notes=["analizada"])

    monkeypatch.setattr(vision, "get_settings", lambda: settings)
    monkeypatch.setattr(vision, "validate_image_upload", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        vision,
        "_open_cache",
        lambda *_args: (_ for _ in ()).throw(OSError("read only")),
    )
    monkeypatch.setattr(vision, "_generate_analysis", lambda *_args: expected)

    assert vision.analyze_image_bytes(b"photo", "image/png") == expected


def test_all_vision_attempts_fail_without_returning_invented_food(monkeypatch, tmp_path):
    settings = _settings(tmp_path)

    monkeypatch.setattr(vision, "get_settings", lambda: settings)
    monkeypatch.setattr(vision, "validate_image_upload", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(vision, "_load_cached_analysis", lambda *_args: None)
    monkeypatch.setattr(
        vision,
        "_generate_analysis",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("429 RESOURCE_EXHAUSTED")),
    )

    try:
        vision.analyze_image_bytes(b"photo", "image/webp")
    except RuntimeError as exc:
        assert "No configured vision model" in str(exc)
    else:
        raise AssertionError("The vision action must fail instead of inventing ingredients.")
