from __future__ import annotations

from pathlib import Path

from scripts.patch_utils import replace_once


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "streamlit_app" / "app.py"
VISION_PATH = PROJECT_ROOT / "src" / "fridgechef" / "vision.py"
RECIPE_IMAGES_PATH = PROJECT_ROOT / "src" / "fridgechef" / "recipe_images.py"


def _replace_if_needed(
    source: str,
    old: str,
    new: str,
    description: str,
) -> str:
    """Apply one exact migration while remaining safe to run repeatedly."""
    if new in source:
        return source
    return replace_once(source, old, new, description)


def _patch_recipe_ingredients(source: str) -> str:
    """Keep recipe ingredient lists compact without changing recipe content."""
    old = '''            st.markdown("### Ingredientes")
            for ingredient in recipe.ingredients_used:
                st.markdown(f"- {sentence_case(ingredient)}")
'''
    new = '''            # Keep long ingredient lists compact on phones, tablets and desktops.
            # The native Streamlit expander preserves accessibility and responsive width
            # without introducing custom JavaScript or changing the recipe card layout.
            with st.expander("🥕 Ingredientes", expanded=False):
                for ingredient in recipe.ingredients_used:
                    st.markdown(f"- {sentence_case(ingredient)}")
'''
    return _replace_if_needed(
        source,
        old,
        new,
        "recipe ingredient list",
    )


def _patch_vision_logging(source: str) -> str:
    """Treat recovered provider attempts as diagnostics instead of warnings."""
    old = '''                _LOGGER.warning("Vision attempt failed for %s@%s: %s", model_name, location, summary)
'''
    new = '''                # A failed candidate is expected while the fallback chain is still running.
                # Keep it at INFO so production logs reserve warnings for user-visible failures.
                _LOGGER.info("Vision candidate unavailable for %s@%s: %s", model_name, location, summary)
'''
    return _replace_if_needed(
        source,
        old,
        new,
        "recoverable vision log",
    )


def _patch_recipe_image_logging(source: str) -> str:
    """Avoid warning noise when another model or the local fallback succeeds."""
    old_attempt = '''            _LOGGER.warning(
                "Recipe image cloud attempt failed for %s: %s: %s",
                model_name,
                type(exc).__name__,
                summary,
            )
'''
    new_attempt = '''            # Individual provider failures are expected while another image
            # model can still complete the request, so keep them as diagnostics.
            _LOGGER.info(
                "Recipe image candidate unavailable for %s: %s: %s",
                model_name,
                type(exc).__name__,
                summary,
            )
'''
    source = _replace_if_needed(
        source,
        old_attempt,
        new_attempt,
        "recoverable recipe image attempt log",
    )

    old_fallback = '''        _LOGGER.warning(
            "Cloud recipe image unavailable for '%s'; using local fallback: %s",
            recipe.title,
            summary,
        )
'''
    new_fallback = '''        # The local card fulfils the requested image contract, so this is a
        # successful recovery path rather than an operational warning.
        _LOGGER.info(
            "Cloud recipe image unavailable for '%s'; local fallback selected: %s",
            recipe.title,
            summary,
        )
'''
    return _replace_if_needed(
        source,
        old_fallback,
        new_fallback,
        "local recipe image fallback log",
    )


def _write_if_changed(path: Path, updated: str) -> None:
    """Write migrated source only when its contents actually changed."""
    current = path.read_text(encoding="utf-8")
    if updated != current:
        path.write_text(updated, encoding="utf-8")


def apply() -> None:
    """Materialize the responsive ingredient UI and recovered-provider logging."""
    app_source = APP_PATH.read_text(encoding="utf-8")
    _write_if_changed(APP_PATH, _patch_recipe_ingredients(app_source))

    vision_source = VISION_PATH.read_text(encoding="utf-8")
    _write_if_changed(VISION_PATH, _patch_vision_logging(vision_source))

    recipe_image_source = RECIPE_IMAGES_PATH.read_text(encoding="utf-8")
    _write_if_changed(
        RECIPE_IMAGES_PATH,
        _patch_recipe_image_logging(recipe_image_source),
    )


if __name__ == "__main__":
    apply()
