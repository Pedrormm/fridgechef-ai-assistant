from pathlib import Path


APP_PATH = Path("streamlit_app/app.py")
DOCKERFILES = (Path("Dockerfile"), Path("Dockerfile.git.nas"))


def _app_source() -> str:
    return APP_PATH.read_text(encoding="utf-8")


def test_app_loads_the_saved_theme_for_new_browser_sessions():
    source = _app_source()

    assert "load_visual_theme_preference" in source
    assert "saved_theme = (" in source
    assert '"selected_visual_theme": saved_theme' in source


def test_theme_selector_persists_changes_through_a_callback():
    source = _app_source()

    assert "def _commit_theme_selection(widget_key: str)" in source
    assert "save_visual_theme_preference" in source
    assert "on_change=_commit_theme_selection" in source
    assert 'args=(widget_key,)' in source


def test_container_builds_use_materialized_application_source():
    """Container builds must package validated source instead of rewriting it."""
    app_source = _app_source()
    assert "load_visual_theme_preference" in app_source
    assert "save_visual_theme_preference" in app_source

    for dockerfile in DOCKERFILES:
        source = dockerfile.read_text(encoding="utf-8")
        assert "COPY ." in source
        assert "python -m scripts.patch_theme_persistence" not in source


def test_ci_detects_materialization_drift_before_building_images():
    workflow = Path(".github/workflows/apply-additive-multi-input.yml").read_text(
        encoding="utf-8"
    )

    assert "python -m scripts.patch_production_resilience" in workflow
    assert "git diff --exit-code" in workflow
