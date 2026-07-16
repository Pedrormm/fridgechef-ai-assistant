from __future__ import annotations

from pathlib import Path

from scripts.patch_utils import replace_once, replace_regex_once


APP_PATH = Path("streamlit_app/app.py")


def apply_patch() -> None:
    """Persist the selected visual theme in the shared SQLite preference table."""
    text = APP_PATH.read_text(encoding="utf-8")
    marker = "from src.fridgechef.app_preferences import ("
    if marker in text:
        print("Visual theme persistence patch is already applied.")
        return

    text = replace_once(
        text,
        "from src.fridgechef.blink_camera import capture_blink_photo_sync\n",
        "from src.fridgechef.app_preferences import (\n"
        "    load_visual_theme_preference,\n"
        "    save_visual_theme_preference,\n"
        ")\n"
        "from src.fridgechef.blink_camera import capture_blink_photo_sync\n",
        "visual theme preference import",
    )

    text = replace_once(
        text,
        "    saved_language = load_language_preference() if is_new_browser_session else current_language()\n"
        "    defaults = {\n",
        "    saved_language = load_language_preference() if is_new_browser_session else current_language()\n"
        "    saved_theme = (\n"
        "        load_visual_theme_preference()\n"
        "        if is_new_browser_session\n"
        "        else st.session_state.get(\"selected_visual_theme\", \"current\")\n"
        "    )\n"
        "    defaults = {\n",
        "initial visual theme load",
    )

    text = replace_once(
        text,
        '        "selected_visual_theme": "current",\n',
        '        "selected_visual_theme": saved_theme,\n',
        "visual theme session default",
    )

    selector_block = '''def _commit_theme_selection(widget_key: str) -> None:
    """Persist the selected theme before Streamlit reruns the application."""
    selected_theme = save_visual_theme_preference(st.session_state.get(widget_key))
    st.session_state["selected_visual_theme"] = selected_theme


def render_theme_selector() -> str:
    """Show the visual themes and restore the saved choice after a full refresh.

    Streamlit Session State is reset when the browser reconnects, so the selected
    theme is loaded from SQLite during ``init_state``. The selectbox callback
    writes each change before the normal top-to-bottom rerun applies the new CSS.
    """
    options = theme_options()
    current = st.session_state.get("selected_visual_theme", "current")
    if current not in options:
        current = save_visual_theme_preference("current")
        st.session_state["selected_visual_theme"] = current

    widget_key = f"selected_visual_theme_widget_v3_{current_language()}"
    with st.sidebar:
        st.selectbox(
            "Tema visual",
            options,
            index=options.index(current),
            key=widget_key,
            format_func=theme_label,
            help="Cambia únicamente la estética de la aplicación. No modifica tus alimentos ni tus preferencias.",
            on_change=_commit_theme_selection,
            args=(widget_key,),
        )
        st.divider()
    return st.session_state.get("selected_visual_theme", "current")


def build_profile'''
    text = replace_regex_once(
        text,
        r"def render_theme_selector\(\) -> str:.*?\n\ndef build_profile",
        selector_block,
        "visual theme selector",
    )

    APP_PATH.write_text(text, encoding="utf-8")
    print("Applied persistent visual theme selection.")


if __name__ == "__main__":
    apply_patch()
