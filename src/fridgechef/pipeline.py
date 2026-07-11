from __future__ import annotations

from collections.abc import Callable

from src.fridgechef.availability import assess_recipe_readiness
from src.fridgechef.models import PipelineResult, UserProfile
from src.fridgechef.persistence import save_image_if_allowed, save_session_if_allowed
from src.fridgechef.policy import validate_recipe_response
from src.fridgechef.recipe_planner import generate_recipes
from src.fridgechef.vision import analyze_image_bytes

ProgressCallback = Callable[[str], None]


class FridgeChefPipeline:
    """Coordinates vision, recipe generation, guardrails and optional persistence."""

    def _progress(self, callback: ProgressCallback | None, message: str) -> None:
        """Send progress messages to the UI without coupling the pipeline to Streamlit."""
        if callback:
            callback(message)

    def run(
        self,
        manual_ingredients: list[str],
        profile: UserProfile,
        image_bytes: bytes | None = None,
        mime_type: str = "image/jpeg",
        allow_save_session: bool = False,
        allow_save_image: bool = False,
        progress_callback: ProgressCallback | None = None,
    ) -> PipelineResult:
        fridge_analysis = None
        image_uri = None
        warnings: list[str] = []

        self._progress(progress_callback, "Preparando la información que has añadido.")

        if image_bytes:
            self._progress(progress_callback, "Revisando la foto para reconocer alimentos visibles.")
            fridge_analysis = analyze_image_bytes(image_bytes, mime_type)

            self._progress(progress_callback, "Comprobando si la imagen se debe guardar de forma opcional.")
            image_uri = save_image_if_allowed(image_bytes, mime_type, allow_save_image)

        self._progress(progress_callback, "Comprobando si hay alimentos suficientes para cocinar sin inventar nada.")
        readiness = assess_recipe_readiness(manual_ingredients, fridge_analysis)

        if readiness.can_generate:
            self._progress(progress_callback, "Buscando recetas que encajen con tus ingredientes y preferencias.")
        else:
            self._progress(progress_callback, "He reconocido la entrada, pero no hay suficientes ingredientes fiables para crear recetas.")

        recipe_response = generate_recipes(manual_ingredients, profile, fridge_analysis)

        self._progress(progress_callback, "Revisando alergias, intolerancias y restricciones antes de mostrar el resultado.")
        warnings.extend(validate_recipe_response(recipe_response, profile))

        session_payload = {
            "manual_ingredients": manual_ingredients,
            "profile": profile.model_dump(),
            "fridge_analysis": fridge_analysis.model_dump() if fridge_analysis else None,
            "recipe_response": recipe_response.model_dump(),
            "image_uri": image_uri,
        }

        self._progress(progress_callback, "Preparando el resultado final.")
        session_id = save_session_if_allowed(session_payload, allow_save_session)

        return PipelineResult(
            fridge_analysis=fridge_analysis,
            recipe_response=recipe_response,
            persisted_session_id=session_id,
            persisted_image_uri=image_uri,
            warnings=warnings,
        )
