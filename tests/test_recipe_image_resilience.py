import base64
from io import BytesIO
from types import SimpleNamespace

from PIL import Image

from src.fridgechef import recipe_images
from src.fridgechef.models import RecipeItem, UserProfile


def _recipe() -> RecipeItem:
    return RecipeItem(
        title="Patatas salteadas con tomate",
        description="Una receta sencilla y rápida.",
        why_this_recipe="Aprovecha los alimentos disponibles.",
        time_min=20,
        servings=2,
        category="Plato principal",
        cuisine="Casera",
        ingredients_used=["Patatas", "Tomate"],
        steps=["Corta las patatas.", "Cocina todo junto."],
        anti_waste_tip="Guarda las sobras en frío.",
    )


def test_local_fallback_guarantees_one_renderable_image(monkeypatch, tmp_path):
    settings = SimpleNamespace(
        recipe_images_enabled=True,
        image_model_name="gemini-3.1-flash-image",
        image_fallback_models="gemini-2.5-flash-image",
        local_database_path=str(tmp_path / "fridgechef.db"),
    )
    monkeypatch.setattr(recipe_images, "get_settings", lambda: settings)
    monkeypatch.setattr(
        recipe_images,
        "_try_generate_image",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("429 RESOURCE_EXHAUSTED")),
    )

    enriched = recipe_images.generate_recipe_image(
        _recipe(),
        UserProfile(),
        use_cache=False,
    )

    image_bytes = base64.b64decode(enriched.image_base64)
    with Image.open(BytesIO(image_bytes)) as image:
        assert image.format == "JPEG"
        assert image.width >= 1000
        assert image.height >= 700

    assert enriched.image_mime_type == "image/jpeg"
    assert enriched.image_generation_error == ""


def test_retired_imagen_models_are_not_requested():
    settings = SimpleNamespace(
        image_model_name="imagen-4.0-generate-001",
        image_fallback_models=(
            "imagen-3.0-generate-002,gemini-3.1-flash-image,gemini-2.5-flash-image"
        ),
    )

    models = recipe_images._ordered_image_models(settings)

    assert models == ["gemini-3.1-flash-image", "gemini-2.5-flash-image"]
    assert not any(model.startswith("imagen-") for model in models)
