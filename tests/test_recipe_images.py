from __future__ import annotations

import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.fridgechef.models import RecipeItem, RecipeResponse, UserProfile
from src.fridgechef.recipe_images import (
    _extract_image_from_generate_content_response,
    attach_recipe_images,
    build_recipe_image_prompt,
)


def sample_profile() -> UserProfile:
    return UserProfile(servings=2)


def sample_recipe(title: str = "Minihamburguesa casera") -> RecipeItem:
    return RecipeItem(
        title=title,
        description="Plato casero rápido y sabroso.",
        why_this_recipe="Aprovecha los ingredientes disponibles.",
        time_min=25,
        ingredients_used=["carne picada de cerdo", "huevo", "tomate frito"],
        steps=["Mezcla.", "Cocina.", "Sirve."],
        anti_waste_tip="Guarda la salsa restante.",
    )


def test_build_recipe_image_prompt_mentions_title_and_ingredients() -> None:
    recipe = sample_recipe()
    prompt = build_recipe_image_prompt(recipe, sample_profile())
    assert recipe.title in prompt
    assert "carne picada de cerdo" in prompt.lower()
    assert "ultrarrealista" in prompt.lower() or "hiperrealista" in prompt.lower()


def test_extract_inline_image_from_gemini_generate_content_shape() -> None:
    class InlineData:
        mime_type = "image/jpeg"
        data = b"fake-image"

    class Part:
        inline_data = InlineData()

    class Content:
        parts = [Part()]

    class Candidate:
        content = Content()

    class Response:
        candidates = [Candidate()]

    data, mime = _extract_image_from_generate_content_response(Response())
    assert data == b"fake-image"
    assert mime == "image/jpeg"


def test_attach_recipe_images_saves_generation_result(monkeypatch) -> None:
    recipe = sample_recipe()
    response = RecipeResponse(recipes=[recipe], recognized_ingredients=["carne picada de cerdo"], global_explanation="")

    image_bytes = b"fake-jpeg-bytes"
    fake_result = recipe.model_copy(update={
        "image_base64": base64.b64encode(image_bytes).decode("ascii"),
        "image_mime_type": "image/jpeg",
        "image_generation_error": "",
    })

    import src.fridgechef.recipe_images as recipe_images_module

    monkeypatch.setattr(recipe_images_module, "generate_recipe_image", lambda *args, **kwargs: fake_result)
    monkeypatch.setattr(recipe_images_module, "_load_cached_image", lambda *args, **kwargs: None)

    updated = attach_recipe_images(response, sample_profile(), enabled=True)
    assert updated.recipes[0].image_base64 == base64.b64encode(image_bytes).decode("ascii")
    assert updated.recipes[0].image_generation_error == ""


def test_attach_recipe_images_keeps_user_facing_error(monkeypatch) -> None:
    recipe = sample_recipe()
    response = RecipeResponse(recipes=[recipe], recognized_ingredients=["carne picada de cerdo"], global_explanation="")

    import src.fridgechef.recipe_images as recipe_images_module

    monkeypatch.setattr(
        recipe_images_module,
        "generate_recipe_image",
        lambda *args, **kwargs: recipe.model_copy(update={"image_generation_error": "No se ha podido generar la imagen de esta receta ahora mismo."}),
    )
    monkeypatch.setattr(recipe_images_module, "_load_cached_image", lambda *args, **kwargs: None)

    updated = attach_recipe_images(response, sample_profile(), enabled=True)
    assert updated.recipes[0].image_base64 == ""
    assert updated.recipes[0].image_generation_error == "No se ha podido generar la imagen de esta receta ahora mismo."
