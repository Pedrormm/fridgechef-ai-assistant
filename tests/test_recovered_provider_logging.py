from pathlib import Path


VISION_PATH = Path("src/fridgechef/vision.py")
RECIPE_IMAGES_PATH = Path("src/fridgechef/recipe_images.py")


def test_recovered_vision_candidates_do_not_emit_operational_warnings():
    source = VISION_PATH.read_text(encoding="utf-8")

    assert '_LOGGER.info("Vision candidate unavailable for %s@%s: %s"' in source
    assert '_LOGGER.warning("Vision attempt failed for %s@%s: %s"' not in source


def test_recovered_recipe_image_candidates_do_not_emit_operational_warnings():
    source = RECIPE_IMAGES_PATH.read_text(encoding="utf-8")

    assert '"Recipe image candidate unavailable for %s: %s: %s"' in source
    assert '"Recipe image cloud attempt failed for %s: %s: %s"' not in source


def test_successful_local_image_fallback_is_logged_as_diagnostic_information():
    source = RECIPE_IMAGES_PATH.read_text(encoding="utf-8")

    assert '"Cloud recipe image unavailable for \'%s\'; local fallback selected: %s"' in source
    assert '"Cloud recipe image unavailable for \'%s\'; using local fallback: %s"' not in source
