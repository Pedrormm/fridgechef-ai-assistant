from __future__ import annotations

import base64
import html
import mimetypes
import re
import sys
from pathlib import Path
from typing import Callable, Literal

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from src.fridgechef.blink_camera import capture_blink_photo_sync
from src.fridgechef.config import get_settings
from src.fridgechef.device_camera import rear_camera_input
from src.fridgechef.fridge_qa import answer_fridge_question
from src.fridgechef.input_pipeline import (
    PreparedImageInput,
    build_incoming_inventory,
    merge_fridge_analyses,
)
from src.fridgechef.i18n import (
    install_streamlit_i18n,
    language_option_label,
    load_language_preference,
    normalise_language,
    save_language_preference,
    translate_text,
)
from src.fridgechef.inventory import (
    apply_inventory_update,
    friendly_state_label,
    inventory_from_inputs,
    inventory_to_recipe_ingredients,
)
from src.fridgechef.models import FridgeAnalysis, InventoryItem, InventoryUpdateResult, RecipeResponse, UserProfile
from src.fridgechef.inventory_editor import (
    build_delete_confirmation_text,
    inventory_state_options,
    inventory_state_select_label,
    validate_inventory_edit,
)
from src.fridgechef.persistence import (
    InventoryPersistenceResult,
    clear_inventory_state,
    load_inventory_state,
    save_inventory_state,
    save_session_if_allowed,
)
from src.fridgechef.preferences import PreferenceValidationError, validate_profile_preferences
from src.fridgechef.quantities import (
    display_quantity_label,
    format_quantity_parts,
    parse_quantity_label,
)
from src.fridgechef.recipe_images import attach_recipe_images
from src.fridgechef.recipe_planner import clean_user_text, generate_recipes, sentence_case
from src.fridgechef.security import ImageValidationError, validate_image_upload
from src.fridgechef.text_parser import ManualIngredientParseResult, parse_manual_ingredients
from src.fridgechef.theme import build_theme_css, theme_label, theme_options
from src.fridgechef.ui_keys import inventory_action_key
from src.fridgechef.vision import analyze_image_bytes

settings = get_settings()

st.set_page_config(
    page_title="FridgeChef AI Assistant",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get help": None,
        "Report a bug": None,
        "About": None,
    },
)

try:
    # Viewer mode keeps the native sidebar control available on desktop and mobile.
    # Hiding the whole Streamlit header also hides the only reliable sidebar
    # toggle, so we keep the lightweight viewer chrome and hide only deployment
    # affordances with CSS below.
    st.set_option("client.toolbarMode", "viewer")
except Exception:
    pass

UpdateMode = Literal["replace", "add"]
InputSource = Literal["manual", "upload", "device_camera", "internal_camera"]
ActionResult = tuple[FridgeAnalysis | None, InventoryUpdateResult | None, ManualIngredientParseResult]




def current_language() -> str:
    """Return the currently selected interface language."""
    return normalise_language(st.session_state.get("app_language", "es"))


def t(value: object) -> str:
    """Translate visible text according to the selected language."""
    return translate_text(value, current_language())


def _html_text(value: object) -> str:
    """Translate and escape text before it is injected into small HTML blocks."""
    return html.escape(t(value), quote=False)


def _css_content(value: object) -> str:
    """Translate text and make it safe for a CSS content string."""
    return t(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _language_selector_css() -> str:
    """Keep the language selector compact and device-specific.

    Desktop/tablet shows only the language names. Mobile shows the same
    selector with ES/US text prefixes. Both widgets exist with different
    keys, but CSS displays only the one intended for the current viewport.
    """
    return """
        <style>
            .st-key-fc_language_selector_mobile,
            .st-key-fc-language-selector-mobile {
                display: none !important;
            }
            .st-key-fc_language_selector_desktop,
            .st-key-fc-language-selector-desktop {
                display: block !important;
            }
            .st-key-fc_language_selector_desktop [data-baseweb="select"] > div,
            .st-key-fc-language-selector-desktop [data-baseweb="select"] > div,
            .st-key-fc_language_selector_mobile [data-baseweb="select"] > div,
            .st-key-fc-language-selector-mobile [data-baseweb="select"] > div {
                min-height: 2.55rem !important;
                border-radius: 14px !important;
            }
            @media (max-width: 768px) {
                .st-key-fc_language_selector_desktop,
                .st-key-fc-language-selector-desktop {
                    display: none !important;
                }
                .st-key-fc_language_selector_mobile,
                .st-key-fc-language-selector-mobile {
                    display: block !important;
                }
                .st-key-fc_language_selector_mobile [data-baseweb="select"] > div,
                .st-key-fc-language-selector-mobile [data-baseweb="select"] > div {
                    min-height: 3rem !important;
                }
            }
        </style>
    """


def _commit_language_selection(widget_key: str) -> None:
    """Persist a language selected by one of the responsive selectors."""
    selected_language = normalise_language(st.session_state.get(widget_key))
    if selected_language != current_language():
        save_language_preference(selected_language)
        st.session_state["app_language"] = selected_language


def render_language_selector() -> None:
    """Render a compact, responsive language selector at the top right.

    The desktop selector intentionally shows only the language name. The mobile
    selector shows ES/US text prefixes. No SVG flags, emoji flags or CSS flag
    overlays are used, so the text never overlaps the selectbox label.
    """
    current = current_language()
    language_options = ("es", "en")
    current_index = 1 if current == "en" else 0
    desktop_key = f"app_language_widget_desktop_v8_{current}"
    mobile_key = f"app_language_widget_mobile_v8_{current}"

    _, selector_col = st.columns([0.78, 0.22])
    with selector_col:
        st.markdown(_language_selector_css(), unsafe_allow_html=True)
        with st.container(key="fc_language_selector_desktop"):
            st.selectbox(
                "Idioma",
                language_options,
                index=current_index,
                key=desktop_key,
                format_func=lambda code: language_option_label(code, current_language(), mobile=False),
                label_visibility="collapsed",
                filter_mode=None,
                on_change=_commit_language_selection,
                args=(desktop_key,),
                __skip_i18n=True,
            )
        with st.container(key="fc_language_selector_mobile"):
            st.selectbox(
                "Idioma",
                language_options,
                index=current_index,
                key=mobile_key,
                format_func=lambda code: language_option_label(code, current_language(), mobile=True),
                label_visibility="collapsed",
                filter_mode=None,
                on_change=_commit_language_selection,
                args=(mobile_key,),
                __skip_i18n=True,
            )

class UserFacingError(Exception):
    """Expected validation error that can be shown without technical details."""


def _store_persistence_result(result: InventoryPersistenceResult) -> None:
    """Keep the last database result available for a clear UI status."""
    st.session_state["inventory_persistence_backend"] = result.backend
    st.session_state["inventory_persistence_ok"] = result.success
    st.session_state["inventory_persistence_warning"] = result.warning or ""


def init_state() -> None:
    """Create session state and restore the fridge from the database on refresh."""
    is_new_browser_session = "fridge_inventory" not in st.session_state
    saved_language = load_language_preference() if is_new_browser_session else current_language()
    defaults = {
        "app_language": saved_language,
        "current_image_bytes": None,
        "current_image_mime_type": "image/jpeg",
        "current_image_caption": "",
        "current_image_source": "upload",
        "prepared_images": {},
        "manual_input_version": 0,
        "upload_widget_version": 0,
        "clear_consumed_inputs": False,
        "fridge_inventory": [],
        "last_analysis": None,
        "last_update": None,
        "last_recipes": None,
        "inventory_clear_message": "",
        "inventory_action_message": None,
        "inventory_persistence_backend": "",
        "inventory_persistence_ok": True,
        "inventory_persistence_warning": "",
        "selected_visual_theme": "current",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)

    if is_new_browser_session and settings.allow_chat_persistence:
        result = load_inventory_state()
        st.session_state["fridge_inventory"] = result.inventory
        _store_persistence_result(result)


def apply_app_style() -> None:
    """Apply a polished, neutral design and keep the sidebar accessible.

    Streamlit exposes the sidebar toggle through its header. The rest of the
    framework chrome is hidden, but the sidebar control stays visible because it
    is part of the product navigation on small screens and after manual collapse.
    """
    select_photo_text = _css_content("📷 Seleccionar foto")
    take_photo_text = _css_content("Hacer foto")
    upload_limit_text = _css_content("Hasta 200 MB por foto · JPG, PNG o WEBP")
    upload_drop_text = _css_content("Arrastra una foto aquí o selecciónala desde tu dispositivo")
    camera_permission_text = _css_content("Permite el acceso a la cámara para hacer la foto desde este dispositivo.")
    css = """
        <style>
            :root {
                --fc-primary: #ef5f73;
                --fc-primary-strong: #e6475f;
                --fc-accent: #6ec6a7;
                --fc-warning: #f6a623;
                --fc-danger: #8a4b08;
                --fc-border: rgba(45, 49, 66, 0.12);
                --fc-shadow: 0 18px 48px rgba(45, 49, 66, 0.08);
                --fc-radius: 22px;
            }

            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(239, 95, 115, 0.08), transparent 34rem),
                    radial-gradient(circle at top right, rgba(110, 198, 167, 0.10), transparent 36rem),
                    linear-gradient(180deg, #fbfaf8 0%, #fffefd 100%);
            }

            footer,
            [data-testid="stDeployButton"],
            .stDeployButton,
            #MainMenu,
            [data-testid="stMainMenu"] {
                display: none !important;
                visibility: hidden !important;
                height: 0 !important;
                pointer-events: none !important;
            }

            /*
               Keep Streamlit's native sidebar control intact. The previous
               approach hid the header and then tried to recreate the toggle
               with CSS, but Streamlit can move that control between versions
               and devices. Leaving the native control visible is the most
               stable behaviour and matches the older project version where
               the sidebar worked correctly on both PC and mobile.
            */
            [data-testid="stHeader"] {
                background: transparent !important;
                box-shadow: none !important;
            }

            .block-container {
                max-width: 1180px;
                padding-top: 2.7rem;
                padding-bottom: 4rem;
            }

            [data-testid="stSidebar"] {
                background: linear-gradient(180deg, #f8fafc 0%, #eef8f2 100%);
                border-right: 1px solid rgba(45, 49, 66, 0.08);
                z-index: auto !important;
            }
            section[data-testid="stSidebar"] > div:first-child,
            section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
            section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
                padding-top: 0.35rem !important;
                margin-top: 0 !important;
            }
            section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div:first-child {
                margin-top: 0 !important;
                padding-top: 0 !important;
            }
            section[data-testid="stSidebar"] h1,
            section[data-testid="stSidebar"] h2,
            section[data-testid="stSidebar"] h3 {
                letter-spacing: -0.02em;
            }
            section[data-testid="stSidebar"] h2:first-of-type,
            section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2:first-child {
                margin-top: 0 !important;
                padding-top: 0 !important;
            }
            section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
                gap: 0.72rem !important;
            }

            .hero-card {
                border: 1px solid var(--fc-border);
                border-radius: 28px;
                padding: clamp(1.4rem, 3vw, 2.1rem);
                box-shadow: var(--fc-shadow);
                background: linear-gradient(135deg, rgba(255,255,255,0.96), rgba(245,255,250,0.93));
                margin-bottom: 1.2rem;
            }
            .hero-card h1 {
                font-size: clamp(2rem, 4vw, 3.1rem);
                letter-spacing: -0.045em;
            }
            .muted {
                color: rgba(45, 49, 66, 0.68);
                line-height: 1.65;
            }
            .soft-note {
                border-left: 5px solid var(--fc-warning);
                background: #fff8e6;
                border-radius: 16px;
                padding: 1rem 1.15rem;
                margin: 0.7rem 0 1rem;
                color: #7c4a08;
            }
            .success-soft {
                border-left: 5px solid var(--fc-accent);
                background: #effaf6;
                border-radius: 16px;
                padding: 1rem 1.15rem;
                margin: 0.7rem 0 0.8rem;
                color: #275d4c;
                font-weight: 600;
            }
            .danger-soft {
                border-left: 5px solid #d98324;
                background: #fff7ed;
                border-radius: 16px;
                padding: 1rem 1.15rem;
                margin: 0.7rem 0 0.8rem;
                color: #7c3d00;
                font-weight: 600;
            }
            div.stButton > button {
                border-radius: 15px;
                min-height: 3.05rem;
                font-weight: 750;
                box-shadow: 0 8px 22px rgba(45, 49, 66, 0.08);
                transition: transform .12s ease, box-shadow .12s ease, border-color .12s ease;
            }
            div.stButton > button:hover {
                transform: translateY(-1px);
                box-shadow: 0 12px 28px rgba(45, 49, 66, 0.12);
            }
            div.stButton > button[kind="primary"] {
                background: linear-gradient(135deg, var(--fc-primary), var(--fc-primary-strong));
                border: 0;
            }
            .recipe-card {
                border: 1px solid var(--fc-border);
                border-radius: 24px;
                padding: clamp(1.1rem, 2.5vw, 1.6rem);
                margin: 1rem 0;
                background: rgba(255,255,255,0.88);
                box-shadow: 0 12px 34px rgba(45, 49, 66, 0.06);
            }
            .recipe-image-heading {
                margin-top: 1.2rem;
                margin-bottom: 0.45rem;
                font-weight: 800;
                color: #2d3142;
            }
            .recipe-image-note {
                color: rgba(45, 49, 66, 0.62);
                font-size: 0.92rem;
                margin-top: 0.25rem;
            }

            [data-testid="stFileUploader"],
            [data-testid="stCameraInput"] {
                border: 1px solid rgba(45, 49, 66, 0.08);
                border-radius: 16px;
                background: rgba(246, 247, 251, 0.88);
            }
            [data-testid="stFileUploaderDropzone"] button,
            [data-testid="stFileUploader"] button,
            [data-testid="stCameraInput"] button {
                position: relative !important;
                border-radius: 12px !important;
                min-width: 8.7rem !important;
                overflow: hidden !important;
                font-size: 0 !important;
                color: transparent !important;
                font-weight: 400 !important;
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
                gap: 0.35rem !important;
            }
            [data-testid="stFileUploaderDropzone"] button *,
            [data-testid="stFileUploader"] button *,
            [data-testid="stCameraInput"] button * {
                display: none !important;
                font-size: 0 !important;
                color: transparent !important;
                font-weight: 400 !important;
            }
            [data-testid="stFileUploaderDropzone"] button::after,
            [data-testid="stFileUploader"] button::after {
                content: "{select_photo_text}";
                font-size: 0.95rem !important;
                font-weight: 400 !important;
                color: #2d3142 !important;
            }
            [data-testid="stCameraInput"] button::after {
                content: "{take_photo_text}";
                font-size: 0.95rem !important;
                font-weight: 400 !important;
                color: #2d3142 !important;
            }
            [data-testid="stFileUploaderDropzone"] small,
            [data-testid="stFileUploaderDropzone"] small *,
            [data-testid="stFileUploaderDropzone"] [data-testid="stFileUploaderFileName"],
            [data-testid="stFileUploaderDropzone"] [data-testid="stFileUploaderFileName"] *,
            [data-testid="stFileUploaderDropzone"] > div:last-child,
            [data-testid="stFileUploaderDropzone"] > div:last-child *,
            [data-testid="stFileUploaderDropzone"] section + div,
            [data-testid="stFileUploaderDropzone"] section + div * {
                font-size: 0 !important;
                color: transparent !important;
            }
            [data-testid="stFileUploaderDropzone"] small::after {
                content: "{upload_limit_text}";
                font-size: 0.86rem !important;
                color: rgba(45, 49, 66, 0.58) !important;
            }
            [data-testid="stFileUploaderDropzone"] > div:last-child::after {
                content: "{upload_drop_text}";
                font-size: 0.9rem !important;
                color: rgba(45, 49, 66, 0.62) !important;
            }
            [data-testid="stCameraInput"] p,
            [data-testid="stCameraInput"] a,
            [data-testid="stCameraInput"] span:not(button span) {
                color: transparent !important;
                font-size: 0 !important;
            }
            [data-testid="stCameraInput"] p::after {
                content: "{camera_permission_text}";
                display: block;
                color: rgba(45, 49, 66, 0.74) !important;
                font-size: 1rem !important;
                line-height: 1.45 !important;
            }

            [data-testid="stTooltipHoverTarget"],
            [data-testid="stTooltipIcon"] {
                pointer-events: auto !important;
                position: relative !important;
                z-index: 1000004 !important;
            }

            @media (max-width: 768px) {
                [data-testid="stTooltipContent"],
                [data-testid="stTooltipContent"] *,
                div[role="tooltip"],
                div[role="tooltip"] *,
                div[data-baseweb="popover"][role="tooltip"],
                div[data-baseweb="popover"][role="tooltip"] * {
                    white-space: normal !important;
                    overflow-wrap: break-word !important;
                    word-break: normal !important;
                    line-height: 1.35 !important;
                    text-align: left !important;
                }
                [data-testid="stTooltipContent"],
                div[role="tooltip"],
                div[data-baseweb="popover"][role="tooltip"] {
                    position: fixed !important;
                    left: 0.8rem !important;
                    right: 0.8rem !important;
                    width: auto !important;
                    min-width: 0 !important;
                    max-width: calc(100vw - 1.6rem) !important;
                    transform: none !important;
                    z-index: 1000005 !important;
                    box-sizing: border-box !important;
                }
                section[data-testid="stSidebar"] [data-testid="stTooltipHoverTarget"],
                section[data-testid="stSidebar"] [data-testid="stTooltipIcon"] {
                    pointer-events: auto !important;
                    touch-action: manipulation !important;
                    z-index: 1000006 !important;
                }
                .block-container {
                    padding: 4.3rem 0.85rem 3rem;
                }
                .hero-card {
                    border-radius: 20px;
                    padding: 1.2rem;
                }
                div.stButton > button {
                    min-height: 3.1rem;
                }

                /*
                   On phones Streamlit renders the sidebar as a slide-over panel.
                   The main page must stay behind it, otherwise cards and headings
                   are painted over the preferences panel and taps go to the wrong
                   element. Keeping this rule mobile-only avoids changing the PC
                   layout that is already working well.
                */
                section[data-testid="stSidebar"] {
                    z-index: 999999 !important;
                    background: linear-gradient(180deg, #f8fafc 0%, #eef8f2 100%) !important;
                    box-shadow: 14px 0 34px rgba(45, 49, 66, 0.22) !important;
                    border-right: 1px solid rgba(45, 49, 66, 0.16) !important;
                }
                section[data-testid="stSidebar"] > div:first-child,
                section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
                section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
                    background: linear-gradient(180deg, #f8fafc 0%, #eef8f2 100%) !important;
                    opacity: 1 !important;
                }
                section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
                    padding-left: 1rem !important;
                    padding-right: 1rem !important;
                }
                section[data-testid="stSidebar"] details,
                section[data-testid="stSidebar"] details > summary,
                section[data-testid="stSidebar"] [data-testid="stExpander"] {
                    position: relative !important;
                    z-index: 1000000 !important;
                    background: rgba(255, 255, 255, 0.92) !important;
                }
                section[data-testid="stSidebar"] input,
                section[data-testid="stSidebar"] textarea,
                section[data-testid="stSidebar"] button,
                section[data-testid="stSidebar"] label {
                    pointer-events: auto !important;
                }
                /*
                   On mobile there must be one clear sidebar control. Streamlit
                   exposes different controls depending on whether the sidebar
                   is open or closed, so we pin every sidebar control to the
                   same position instead of letting two separate chevrons appear
                   in different places.
                */
                [data-testid="stSidebarCollapsedControl"],
                [data-testid="collapsedControl"],
                [data-testid="stExpandSidebarButton"],
                [data-testid="stSidebarCollapseButton"],
                section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] {
                    position: fixed !important;
                    top: 0.75rem !important;
                    left: 0.75rem !important;
                    z-index: 1000002 !important;
                    pointer-events: auto !important;
                    display: inline-flex !important;
                    visibility: visible !important;
                    opacity: 1 !important;
                    background: rgba(255, 255, 255, 0.86) !important;
                    border-radius: 0.75rem !important;
                    box-shadow: 0 6px 18px rgba(45, 49, 66, 0.12) !important;
                }
                [data-testid="stExpandSidebarButton"] button,
                [data-testid="stSidebarCollapseButton"] button,
                [data-testid="stSidebarCollapsedControl"] button,
                [data-testid="collapsedControl"] button {
                    pointer-events: auto !important;
                }
            }
        </style>
        """
    css = (
        css.replace("{select_photo_text}", select_photo_text)
        .replace("{take_photo_text}", take_photo_text)
        .replace("{upload_limit_text}", upload_limit_text)
        .replace("{upload_drop_text}", upload_drop_text)
        .replace("{camera_permission_text}", camera_permission_text)
    )
    st.markdown(css, unsafe_allow_html=True)

def get_inventory() -> list[InventoryItem]:
    """Return the saved fridge inventory as Pydantic objects."""
    inventory: list[InventoryItem] = []
    for raw_item in st.session_state.get("fridge_inventory", []):
        if isinstance(raw_item, InventoryItem):
            inventory.append(raw_item)
        else:
            inventory.append(InventoryItem.model_validate(raw_item))
    return inventory


def set_inventory(items: list[InventoryItem], persist: bool = False) -> None:
    """Update session state and, when requested, the durable database record."""
    raw_inventory = [item.model_dump() for item in items]
    st.session_state["fridge_inventory"] = raw_inventory
    if persist and settings.allow_chat_persistence:
        _store_persistence_result(save_inventory_state(raw_inventory))


def clear_inventory(remember_fridge: bool) -> str:
    """Remove the saved fridge list without exposing persistence errors to the UI.

    The button can be pressed even when there is nothing saved. That should be a
    harmless action, not an exception. We also keep external persistence best
    effort only: the local interface must remain stable even if Firestore is not
    configured during a demo or local run.
    """
    had_saved_items = bool(get_inventory())

    set_inventory([])
    if remember_fridge and settings.allow_chat_persistence:
        _store_persistence_result(clear_inventory_state())
    st.session_state["last_update"] = None
    st.session_state["last_analysis"] = None
    st.session_state["last_recipes"] = None

    if not had_saved_items:
        return "La nevera guardada ya estaba vacía. No había alimentos que borrar."

    try:
        save_session_if_allowed({"event": "inventory_cleared"}, allow_save=remember_fridge)
    except Exception:
        # Clearing the visible fridge is the important user action here. If the
        # optional cloud log is unavailable, we keep the UI clean and continue.
        pass

    return "He vaciado la lista de alimentos guardados en la nevera."


def show_clear_inventory_dialog(remember_fridge: bool) -> None:
    """Ask for confirmation before deleting the saved fridge list."""

    def _confirm_content() -> None:
        already_empty = not bool(get_inventory())

        if already_empty:
            st.markdown("### " + t("La nevera guardada ya está vacía"))
            st.write(t("Ahora mismo no hay alimentos guardados que borrar."))
            if st.button(t("Entendido"), type="primary", use_container_width=True):
                st.session_state["inventory_clear_message"] = clear_inventory(remember_fridge)
                st.rerun()
            return

        st.markdown("### " + t("¿Quieres vaciar la nevera guardada?"))
        st.write(
            t(
                "Se eliminará la lista de alimentos que tengo recordada para esta sesión. "
                "No afectará a las fotos ni a los ingredientes que escribas después."
            )
        )
        col_cancel, col_confirm = st.columns(2)
        with col_cancel:
            if st.button(t("Cancelar"), use_container_width=True):
                st.rerun()
        with col_confirm:
            if st.button(t("Sí, vaciar la lista"), type="primary", use_container_width=True):
                st.session_state["inventory_clear_message"] = clear_inventory(remember_fridge)
                st.rerun()

    if hasattr(st, "dialog"):
        @st.dialog(t("Vaciar nevera guardada"))
        def _dialog() -> None:
            _confirm_content()

        _dialog()
    else:  # pragma: no cover - compatibility for older Streamlit versions
        with st.container(border=True):
            _confirm_content()


def store_prepared_image(
    image_data: bytes,
    image_mime_type: str,
    caption: str,
    source: InputSource,
) -> None:
    """Keep one image per input channel so every prepared source can be analyzed."""
    prepared = dict(st.session_state.get("prepared_images", {}))
    prepared[source] = {
        "image_bytes": image_data,
        "mime_type": image_mime_type,
        "caption": caption,
    }
    st.session_state["prepared_images"] = prepared


def get_prepared_image(source: InputSource) -> PreparedImageInput | None:
    """Return one prepared image without affecting the other input channels."""
    payload = st.session_state.get("prepared_images", {}).get(source)
    if not isinstance(payload, dict) or not payload.get("image_bytes"):
        return None
    return PreparedImageInput(
        source=source,
        image_bytes=payload["image_bytes"],
        mime_type=str(payload.get("mime_type") or "image/jpeg"),
        caption=str(payload.get("caption") or "Foto preparada"),
    )


def get_prepared_images() -> list[PreparedImageInput]:
    """Return every prepared image in a stable processing order."""
    images: list[PreparedImageInput] = []
    for source in ("upload", "device_camera", "internal_camera"):
        image = get_prepared_image(source)
        if image is not None:
            images.append(image)
    return images


def clear_prepared_image(source: InputSource) -> None:
    """Remove one image while preserving the remaining prepared inputs."""
    prepared = dict(st.session_state.get("prepared_images", {}))
    prepared.pop(source, None)
    st.session_state["prepared_images"] = prepared
    if source == "upload":
        st.session_state["upload_widget_version"] = int(
            st.session_state.get("upload_widget_version", 0)
        ) + 1


def reset_consumed_inputs_if_needed() -> None:
    """Clear persisted inputs on the next rerun to prevent accidental double counting."""
    if not st.session_state.get("clear_consumed_inputs"):
        return
    st.session_state["prepared_images"] = {}
    st.session_state["manual_input_version"] = int(
        st.session_state.get("manual_input_version", 0)
    ) + 1
    st.session_state["upload_widget_version"] = int(
        st.session_state.get("upload_widget_version", 0)
    ) + 1
    st.session_state["clear_consumed_inputs"] = False


def capture_internal_camera_with_feedback() -> None:
    """Capture a fresh image from the fridge camera with friendly progress text."""
    with st.status("Conectando con la cámara interna", expanded=True) as status:
        try:
            status.write(t("Preparando la conexión con la cámara que está dentro de la nevera."))
            status.write(t("Solicitando una foto nueva para evitar usar una imagen anterior."))
            output = capture_blink_photo_sync(
                settings.blink_auth_file,
                settings.blink_output_file,
                settings.blink_max_stale_seconds,
            )
            status.write(t("Comprobando que la foto se ha guardado correctamente."))
            image_bytes = Path(output).read_bytes()
            validate_image_upload(image_bytes, "image/jpeg", settings.max_image_mb)
            store_prepared_image(image_bytes, "image/jpeg", "Foto de cámara interna", "internal_camera")
            status.update(label=t("Foto realizada"), state="complete", expanded=False)
            st.success("Foto realizada correctamente.")
        except Exception as exc:
            status.update(label=t("No he podido realizar la foto"), state="error", expanded=False)
            st.error(
                "No he podido realizar una foto nueva con la cámara interna. "
                "Revisa que esté conectada, con batería o alimentación, y vuelve a intentarlo."
            )


def can_offer_device_camera() -> bool:
    """Show browser camera capture only when it is safe to render it.

    Rendering ``st.camera_input`` can make desktop browsers enumerate camera
    devices and, on some Windows setups, trigger Phone Link or other camera apps.
    The tab is therefore hidden on desktop by default and only appears on mobile
    or tablet browsers. A local developer can still force it with
    ``?device_camera=1`` when testing intentionally.
    """
    try:
        query_value = str(st.query_params.get("device_camera", "")).lower()
        if query_value in {"1", "true", "yes", "on"}:
            return True

        headers = getattr(st, "context", None).headers if hasattr(st, "context") else {}
        user_agent = str(headers.get("user-agent", "")).lower()
    except Exception:
        user_agent = ""

    if not user_agent:
        return False

    desktop_markers = ("windows nt", "macintosh", "x11", "linux x86_64")
    if any(marker in user_agent for marker in desktop_markers):
        return False

    mobile_markers = ("android", "iphone", "ipad", "ipod", "mobile", "tablet")
    return any(value in user_agent for value in mobile_markers)


def _selector_key(value: str) -> str:
    """Create stable widget keys from display labels."""
    return re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_").lower() or "item"


def _checkbox_key(field_key: str, option: str) -> str:
    """Build one key format for every option in the custom selector."""
    return f"{field_key}_{_selector_key(option)}"


def _current_selector_values(field_key: str, options: list[str], other_label: str) -> list[str]:
    """Read the selector from widget state first, then from the saved summary.

    Streamlit updates widget keys before rerunning the script. The previous
    implementation used only the saved summary key at the top of the function,
    so the collapsed selector title was always one click behind the checkbox
    that the user had just changed. Reading the checkbox keys directly keeps the
    title, the returned profile and the visible selection in sync on the same
    rerun.
    """
    saved_values = list(st.session_state.get(f"selected_{field_key}", []))
    all_options = [*options, other_label]
    has_rendered_checkboxes = any(_checkbox_key(field_key, option) in st.session_state for option in all_options)

    if not has_rendered_checkboxes:
        return [option for option in all_options if option in saved_values]

    return [option for option in all_options if bool(st.session_state.get(_checkbox_key(field_key, option), False))]


def optional_multiselect_with_other(
    field_key: str,
    label: str,
    options: list[str],
    placeholder: str,
    other_label: str,
    other_placeholder: str,
) -> tuple[list[str], str | None]:
    """Render a Spanish multi-selector without stale values or English labels.

    The selector is intentionally built with checkboxes instead of Streamlit's
    native multiselect because the native widget exposes an English bulk-action
    label that the app cannot translate safely. The important part here is that
    the selected values are read from the checkbox widget state at the start of
    each rerun, so the compact title and the values used later by the agents are
    always current.
    """
    state_key = f"selected_{field_key}"
    current = _current_selector_values(field_key, options, other_label)
    summary = placeholder if not current else ", ".join(current[:2]) + ("..." if len(current) > 2 else "")

    # Keep the field name visible even while the compact selector is closed.
    st.markdown(f"**{label}**")

    # Keep the panel open while the user has selected values. That avoids the
    # frustrating mobile behavior where the selector collapsed after every tap
    # and forced the user to open it again to choose several options.
    container = st.expander(summary, expanded=bool(current))

    selected: list[str] = []
    with container:
        st.caption("Puedes elegir una o varias opciones, o dejarlo sin marcar.")
        for option in options:
            checked = st.checkbox(
                option,
                value=option in current,
                key=_checkbox_key(field_key, option),
            )
            if checked:
                selected.append(option)
        other_checked = st.checkbox(
            other_label,
            value=other_label in current,
            key=_checkbox_key(field_key, other_label),
            help="Elige esta opción solo si quieres escribir una preferencia distinta.",
        )
        if other_checked:
            selected.append(other_label)

    # This is the single source consumed by the rest of the app. It is updated
    # during the same rerun as the checkbox tap, so Analyse and Recipe actions
    # always receive the options the user can currently see.
    st.session_state[state_key] = selected

    custom_value: str | None = None
    if other_label in selected:
        # This copy is part of the interface, not an agent decision. The wording
        # for dislikes needs to sound natural because the literal section title
        # is already a complete sentence fragment.
        custom_label = "Especifica lo que no te gusta" if field_key == "dislikes" else f"Especifica {label.lower()}"
        custom_value = st.text_input(
            custom_label,
            key=f"custom_{field_key}",
            placeholder=other_placeholder,
            help="Escribe una opción clara y relacionada con alimentación o recetas.",
        )
    clean_selected = [value for value in selected if value != other_label]
    return clean_selected, custom_value


def render_theme_selector() -> str:
    """Show the three visual themes without changing app behaviour.

    The selected theme is stored in ``selected_visual_theme``. The visible
    selectbox uses a language-versioned widget key so the displayed label is
    rebuilt immediately after switching between Spanish and English.
    """
    options = theme_options()
    current = st.session_state.get("selected_visual_theme", "current")
    if current not in options:
        current = "current"
        st.session_state["selected_visual_theme"] = current

    with st.sidebar:
        selected = st.selectbox(
            "Tema visual",
            options,
            index=options.index(current),
            key=f"selected_visual_theme_widget_v2_{current_language()}",
            format_func=theme_label,
            help="Cambia únicamente la estética de la aplicación. No modifica tus alimentos ni tus preferencias.",
        )
        if selected != current:
            st.session_state["selected_visual_theme"] = selected
            st.rerun()
        st.divider()
    return st.session_state.get("selected_visual_theme", "current")


def build_profile() -> tuple[UserProfile, bool, UpdateMode, bool]:
    """Collect user preferences and persistence choices from the sidebar."""
    with st.sidebar:
        st.header("Perfil y preferencias")
        remember_fridge = st.toggle(
            "Recordar lo que hay en mi nevera",
            value=True,
            help="Guarda la lista de alimentos que vayas analizando para poder consultarla y generar recetas más adelante.",
        )

        if remember_fridge:
            backend = st.session_state.get("inventory_persistence_backend", "")
            persistence_ok = bool(st.session_state.get("inventory_persistence_ok", True))
            if not settings.allow_chat_persistence:
                st.warning("El guardado permanente está desactivado en la configuración.")
            elif not persistence_ok:
                st.warning("No he podido conectar con ninguna base de datos. Revisa los permisos o la carpeta del proyecto.")
            else:
                st.caption("Guarda los alimentos de tu nevera para no tener que volver a introducirlos la próxima vez.")

        update_mode: UpdateMode = "replace"
        if remember_fridge:
            update_choice = st.radio(
                "Al añadir alimentos:",
                options=["replace", "add"],
                index=1,
                format_func=lambda value: "Sustituir por lo que analice ahora" if value == "replace" else "Añadir sin borrar lo anterior",
                help=(
                    "Usa 'Sustituir' si el texto o la foto representan toda la nevera. "
                    "Usa 'Añadir' si solo estás enseñando una parte, como un cajón o una balda."
                ),
            )
            update_mode = "add" if update_choice == "add" else "replace"
            st.caption("Consejo: si analizas solo una parte de la nevera, elige 'Añadir' para no borrar lo anterior.")

        custom_preferences: dict[str, str] = {}
        diet, custom_diet = optional_multiselect_with_other(
            "diet",
            "Dieta",
            ["Vegetariana", "Vegana", "Halal", "Alta en proteína", "Mediterránea"],
            "No sigo una dieta concreta (opcional)",
            "Otra",
            "Ejemplo: baja en sal, sin carne roja...",
        )
        if custom_diet is not None:
            custom_preferences["diet"] = custom_diet

        allergies, custom_allergies = optional_multiselect_with_other(
            "allergies",
            "Alergias",
            ["Huevo", "Leche", "Gluten", "Frutos secos", "Cacahuete", "Marisco", "Pescado", "Soja"],
            "No he indicado alergias (opcional)",
            "Otra",
            "Ejemplo: mostaza, sésamo...",
        )
        if custom_allergies is not None:
            custom_preferences["allergies"] = custom_allergies

        intolerances, custom_intolerances = optional_multiselect_with_other(
            "intolerances",
            "Intolerancias",
            ["Lactosa", "Gluten", "Fructosa", "Sorbitol"],
            "No he indicado intolerancias (opcional)",
            "Otra",
            "Ejemplo: histamina, picante fuerte...",
        )
        if custom_intolerances is not None:
            custom_preferences["intolerances"] = custom_intolerances

        dislikes, custom_dislikes = optional_multiselect_with_other(
            "dislikes",
            "Alimentos que prefiero evitar",
            ["Cebolla", "Ajo", "Pimiento", "Setas", "Picante", "Queso", "Tomate"],
            "No tengo alimentos que prefiera evitar (opcional)",
            "Otro alimento",
            "Ejemplo: cilantro, aceitunas...",
        )
        if custom_dislikes is not None:
            custom_preferences["dislikes"] = custom_dislikes

        goals, custom_goals = optional_multiselect_with_other(
            "goals",
            "Objetivo",
            [
                "Comida rápida",
                "Comida económica",
                "Pérdida de peso",
                "Ganar masa muscular",
                "Meal prep",
                "Cena ligera",
                "Aprovechar sobras",
            ],
            "Sin objetivo concreto (opcional)",
            "Otro",
            "Ejemplo: comida para llevar mañana...",
        )
        if custom_goals is not None:
            custom_preferences["goals"] = custom_goals

        time_limit_min = st.slider(
            "Tiempo máximo por receta (minutos)",
            10,
            90,
            30,
            step=5,
            help="Cuánto tiempo aproximado quieres dedicar como máximo a preparar cada receta sugerida.",
        )
        st.caption("Usaré este tiempo para priorizar recetas rápidas o más elaboradas según lo que elijas.")
        servings = st.slider(
            "Raciones por receta",
            1,
            8,
            2,
            help="Para cuántas personas o platos quieres que estén pensadas las recetas.",
        )
        st.caption("Las recetas se adaptarán a este número de raciones siempre que sea posible.")
        recipe_count = st.slider(
            "Número de recetas",
            1,
            5,
            2,
            help="Cuántas ideas de recetas te gustaría recibir. Si no hay alimentos suficientes, mostraré menos y te lo explicaré.",
        )
        st.caption("Se generará el número solicitado de recetas, siempre que existan opciones realistas.")
        wants_target_recipe = st.toggle("Quiero hacer una receta concreta", value=False)
        target_recipe = st.text_input("Receta concreta", placeholder="Ejemplo: tortilla de patatas") if wants_target_recipe else ""
        extra_context = st.text_area(
            "Contexto adicional",
            placeholder="Ejemplo: hoy he entrenado y quiero algo sencillo con proteína.",
        )
        generate_recipe_images = st.toggle(
            "Generar una imagen por cada receta",
            value=False,
            help="Al activar esta opción, se generará una imagen para cada receta.",
        )
        if generate_recipe_images:
            st.caption("Al activar esta opción, se generará una imagen para cada receta.")
        else:
            st.caption("Si lo desactivas, mostraré solo el texto de las recetas.")

    profile = UserProfile(
        diet=diet,
        allergies=allergies,
        intolerances=intolerances,
        dislikes=dislikes,
        goals=goals,
        time_limit_min=time_limit_min,
        servings=servings,
        recipe_count=recipe_count,
        custom_preferences=custom_preferences,
        wants_target_recipe=wants_target_recipe,
        target_recipe=target_recipe,
        extra_context=extra_context,
    )
    return profile, remember_fridge, update_mode, generate_recipe_images


def show_hero() -> None:
    """Render the application title and product-level value proposition."""
    hero_title = _html_text("🍽️ FridgeChef AI Assistant")
    hero_text = _html_text(
        "Descubre qué tienes en la nevera, mantén tu inventario al día y convierte tus alimentos "
        "en ideas de comida sencillas, útiles y personalizadas."
    )
    st.markdown(
        f"""
        <div class="hero-card">
            <h1 style="margin-bottom: 0.25rem;">{hero_title}</h1>
            <p class="muted" style="font-size: 1.08rem; margin-bottom: 0;">{hero_text}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_fridge_question_box(remember_fridge: bool) -> None:
    """Allow users to ask inventory-related questions when fridge memory is enabled."""
    if not remember_fridge:
        return

    with st.container(border=True):
        st.subheader("Pregunta rápida sobre tu nevera")
        st.caption("Pregúntame qué hay guardado, qué conviene revisar o qué podrías cocinar con lo que ya tengo registrado.")
        question = st.text_input(
            "¿Qué quieres saber?",
            placeholder="Ejemplo: ¿Qué alimentos tengo? ¿Hay algo que deba usar pronto?",
            label_visibility="collapsed",
        )
        if question:
            with st.spinner("Revisando tu nevera guardada..."):
                st.write(answer_fridge_question(question, get_inventory()))


def show_manual_feedback(parse_result: ManualIngredientParseResult) -> None:
    """Explain which manual fragments were accepted or ignored."""
    if parse_result.accepted_items:
        names = [
            f"{sentence_case(item.name)} "
            f"({display_quantity_label({}, item.quantity_label, current_language())})"
            for item in parse_result.accepted_items
        ]
        st.success("Tendré en cuenta: " + ", ".join(names))
    if parse_result.ignored_fragments:
        with st.expander("Texto que no he usado", expanded=False):
            for fragment in parse_result.ignored_fragments:
                st.write(f"• **{clean_user_text(fragment.text)}** — {clean_user_text(fragment.reason)}")


def _inventory_item_key(item: InventoryItem, index: int) -> str:
    """Build a stable UI key for one inventory item card."""
    return f"{index}_{_selector_key(item.normalized_name or item.name)}"


def _find_inventory_index(item_key: str) -> int | None:
    """Find the current position of an item, even after a rerun or reload."""
    for index, item in enumerate(get_inventory()):
        if (item.normalized_name or item.name) == item_key:
            return index
    return None


def _inventory_message(text: str, kind: str = "success") -> None:
    """Store one inventory action message to show after the dialog closes."""
    st.session_state["inventory_action_message"] = {"kind": kind, "text": text}


def show_inventory_action_message() -> None:
    """Render and clear the last edit/delete confirmation message."""
    message = st.session_state.get("inventory_action_message")
    if not isinstance(message, dict):
        return
    text = str(message.get("text") or "")
    kind = str(message.get("kind") or "success")
    if kind == "warning":
        st.warning(text)
    elif kind == "error":
        st.error(text)
    else:
        st.success(text)
    st.session_state["inventory_action_message"] = None


def _validation_messages_for_language(validation) -> tuple[str, ...]:
    """Choose field-agent messages in the active interface language."""
    return validation.messages_en if current_language() == "en" else validation.messages_es


def _replace_inventory_item(index: int, updated_item: InventoryItem) -> bool:
    """Persist an edited inventory item without changing the other cards."""
    inventory = get_inventory()
    if index < 0 or index >= len(inventory):
        return False
    inventory[index] = updated_item
    set_inventory(inventory, persist=True)
    return True


def _delete_inventory_item(index: int) -> InventoryItem | None:
    """Remove one inventory item and persist the new fridge state."""
    inventory = get_inventory()
    if index < 0 or index >= len(inventory):
        return None
    removed = inventory.pop(index)
    set_inventory(inventory, persist=True)
    st.session_state["last_recipes"] = None
    return removed


def show_edit_inventory_dialog(item_key: str) -> None:
    """Open the ingredient editor modal for the selected saved food item."""

    def _content() -> None:
        index = _find_inventory_index(item_key)
        if index is None:
            st.warning("Ese alimento ya no está en la nevera guardada.")
            if st.button("Entendido", type="primary", use_container_width=True):
                st.rerun()
            return

        item = get_inventory()[index]
        base_key = _inventory_item_key(item, index)
        st.write("Modifica solo lo que necesites y guarda los cambios cuando esté todo correcto.")
        new_name = st.text_input(
            "Nombre del alimento",
            value=item.name,
            key=f"edit_name_{base_key}",
            help="Debe ser un alimento o ingrediente claro para la nevera.",
        )
        new_quantity = st.text_input(
            "Cantidad",
            value=item.quantity_label or "Cantidad no indicada",
            key=f"edit_quantity_{base_key}",
            help="Puedes escribir unidades, gramos, litros o dejarlo como cantidad no indicada.",
        )
        state_options = inventory_state_options()
        current_state = item.state if item.state in state_options else "unknown"
        new_state = st.selectbox(
            t("Estado"),
            state_options,
            index=state_options.index(current_state),
            key=f"edit_state_{base_key}",
            format_func=lambda value: inventory_state_select_label(value, current_language()),
            help=t("Elige el estado actual del alimento."),
            filter_mode=None,
            __skip_i18n=True,
        )

        col_cancel, col_save = st.columns(2)
        with col_cancel:
            if st.button("Cancelar", key=f"cancel_edit_{base_key}", use_container_width=True):
                st.rerun()
        with col_save:
            save_clicked = st.button("Guardar cambios", key=f"save_edit_{base_key}", type="primary", use_container_width=True)

        if not save_clicked:
            return

        validation = validate_inventory_edit(new_name, new_quantity, new_state, language=current_language())
        if not validation.ok:
            for message in _validation_messages_for_language(validation):
                st.warning(message, __skip_i18n=True)
            return

        duplicate = next(
            (other for other_index, other in enumerate(get_inventory())
             if other_index != index and other.normalized_name == validation.normalized_name),
            None,
        )
        if duplicate:
            duplicate_message = (
                "Ya existe otro alimento guardado con ese nombre. Edita ese alimento o usa un nombre más específico."
                if current_language() == "es"
                else "Another saved food already has that name. Edit that food or use a more specific name."
            )
            st.warning(duplicate_message, __skip_i18n=True)
            return

        quantity_parts = parse_quantity_label(validation.quantity_label)
        updated_item = item.model_copy(
            update={
                "name": validation.name,
                "normalized_name": validation.normalized_name,
                "quantity": max(1, int(round(quantity_parts.get("unit", 1.0)))),
                "quantity_label": format_quantity_parts(quantity_parts, "es"),
                "quantity_parts": quantity_parts,
                "state": validation.state,
            }
        )
        if not _replace_inventory_item(index, updated_item):
            st.warning("No he podido guardar los cambios porque ese alimento ya no está disponible.")
            return
        _inventory_message("He actualizado el alimento guardado en tu nevera.")
        st.rerun()

    if hasattr(st, "dialog"):
        @st.dialog(t("Editar alimento"))
        def _dialog() -> None:
            _content()

        _dialog()
    else:  # pragma: no cover - older Streamlit compatibility
        with st.container(border=True):
            st.markdown("### " + t("Editar alimento"))
            _content()


def show_delete_inventory_dialog(item_key: str) -> None:
    """Open a confirmation modal before removing one saved food item."""

    def _content() -> None:
        index = _find_inventory_index(item_key)
        if index is None:
            st.warning("Ese alimento ya se ha eliminado de la nevera guardada.")
            if st.button("Entendido", type="primary", use_container_width=True):
                st.rerun()
            return

        item = get_inventory()[index]
        base_key = _inventory_item_key(item, index)
        st.write(build_delete_confirmation_text(item.name, current_language()), __skip_i18n=True)
        st.caption("Esta acción solo elimina este alimento de la lista guardada.")
        col_cancel, col_delete = st.columns(2)
        with col_cancel:
            if st.button("Cancelar", key=f"cancel_delete_{base_key}", use_container_width=True):
                st.rerun()
        with col_delete:
            if st.button("Sí, eliminar el alimento", key=f"confirm_delete_{base_key}", type="primary", use_container_width=True):
                removed = _delete_inventory_item(index)
                if removed is None:
                    _inventory_message("Ese alimento ya no estaba en la nevera guardada.", "warning")
                else:
                    _inventory_message("He eliminado el alimento de tu nevera guardada.")
                st.rerun()

    if hasattr(st, "dialog"):
        @st.dialog(t("Eliminar alimento"))
        def _dialog() -> None:
            _content()

        _dialog()
    else:  # pragma: no cover - older Streamlit compatibility
        with st.container(border=True):
            st.markdown("### " + t("Eliminar alimento"))
            _content()


def show_inventory(
    inventory: list[InventoryItem],
    title: str = "Alimentos guardados",
    editable: bool = False,
    widget_namespace: str | None = None,
) -> None:
    """Display inventory cards with widget keys scoped to this rendered section."""
    st.subheader(title)
    if not inventory:
        st.info("Todavía no hay alimentos guardados. Escribe ingredientes o sube una foto para empezar.")
        return

    key_scope = _selector_key(widget_namespace or f"{title}_{'editable' if editable else 'readonly'}")
    columns = st.columns(2)
    for index, item in enumerate(inventory):
        with columns[index % 2]:
            with st.container(border=True):
                item_key = item.normalized_name or item.name
                base_key = _inventory_item_key(item, index)
                if editable:
                    title_col, edit_col, delete_col = st.columns([0.74, 0.13, 0.13])
                    with title_col:
                        st.markdown(f"#### {sentence_case(item.name)}")
                    with edit_col:
                        if st.button("✏️", key=inventory_action_key(key_scope, "edit", base_key, index), help="Editar alimento", use_container_width=True):
                            show_edit_inventory_dialog(item_key)
                    with delete_col:
                        if st.button("🗑️", key=inventory_action_key(key_scope, "delete", base_key, index), help="Eliminar alimento", use_container_width=True):
                            show_delete_inventory_dialog(item_key)
                else:
                    st.markdown(f"#### {sentence_case(item.name)}")

                quantity_text = display_quantity_label(
                    item.quantity_parts,
                    item.quantity_label,
                    current_language(),
                )
                st.write(f"**Cantidad:** {clean_user_text(quantity_text)}")
                st.write(f"**Estado:** {friendly_state_label(item.state)}")
                if item.expiry_text:
                    st.write(f"**Caducidad visible:** {clean_user_text(item.expiry_text)}")
                if item.sources:
                    st.caption("Origen: " + ", ".join(clean_user_text(source) for source in item.sources))
                public_notes = [clean_user_text(note) for note in item.notes[:2] if clean_user_text(note)]
                for note in public_notes:
                    st.caption(note)


def show_inventory_update(update_result: InventoryUpdateResult) -> None:
    """Explain how the inventory changed after a new analysis."""
    if update_result.mode == "replace":
        message = _html_text("He actualizado la nevera con lo que acabas de analizar.")
    else:
        message = _html_text(
            "He añadido los alimentos nuevos y he sumado las cantidades cuando ya estaban guardados."
        )
    st.markdown(f"<div class='success-soft'>{message}</div>", unsafe_allow_html=True)

    details = []
    if update_result.added:
        details.append("Añadidos: " + ", ".join(sentence_case(item) for item in update_result.added))
    if update_result.updated:
        details.append("Actualizados: " + ", ".join(sentence_case(item) for item in update_result.updated))
    if update_result.removed:
        details.append("Ya no aparecen: " + ", ".join(sentence_case(item) for item in update_result.removed))
    if details:
        st.caption(" · ".join(details))

    for change in update_result.quantity_changes:
        if current_language() == "en":
            previous_quantity = display_quantity_label(
                {}, change.previous_quantity_label, "en"
            )
            incoming_quantity = display_quantity_label(
                {}, change.incoming_quantity_label, "en"
            )
            resulting_quantity = display_quantity_label(
                {}, change.resulting_quantity_label, "en"
            )
            quantity_message = (
                f"{sentence_case(change.name)}: the fridge had {previous_quantity}; "
                f"I added {incoming_quantity}, so it now has {resulting_quantity}."
            )
        else:
            quantity_message = (
                f"{sentence_case(change.name)}: había "
                f"{display_quantity_label({}, change.previous_quantity_label, 'es')}, "
                f"se han añadido "
                f"{display_quantity_label({}, change.incoming_quantity_label, 'es')} "
                f"y ahora hay "
                f"{display_quantity_label({}, change.resulting_quantity_label, 'es')}."
            )
        st.info(quantity_message, __skip_i18n=True)


def show_no_recipe_response(response: RecipeResponse) -> None:
    """Display a friendly no-recipe result when the guardrail blocks generation."""
    reason = response.no_recipe_reason or response.global_explanation
    st.warning(clean_user_text(reason))
    if response.recognized_ingredients:
        st.write("He reconocido:", ", ".join(sentence_case(item) for item in response.recognized_ingredients))
    st.info("Puedes añadir más alimentos o subir una foto con más ingredientes visibles y lo intento de nuevo.")


def _recipe_time_values(recipe) -> tuple[int, int, int]:
    """Return preparation, cooking and total minutes for display."""
    total = max(5, int(recipe.time_min or 30))
    prep = recipe.prep_time_min if recipe.prep_time_min is not None else max(5, round(total * 0.35))
    cook = recipe.cook_time_min if recipe.cook_time_min is not None else max(0, total - prep)
    return int(prep), int(cook), int(total)




def _decode_recipe_image(recipe) -> bytes | None:
    """Return recipe image bytes from the stored base64 payload."""
    encoded = getattr(recipe, "image_base64", "") or ""
    if not encoded:
        return None
    try:
        payload = encoded.split(",", 1)[1] if encoded.startswith("data:") and "," in encoded else encoded
        return base64.b64decode(payload)
    except Exception:
        return None

def show_recipes(response: RecipeResponse, profile: UserProfile, show_images: bool = True) -> None:
    """Render recipe cards using a real recipe-page structure."""
    if not response.recipes:
        show_no_recipe_response(response)
        return

    st.subheader("Recetas sugeridas")
    if response.global_explanation:
        st.info(clean_user_text(response.global_explanation))

    for index, recipe in enumerate(response.recipes, 1):
        prep, cook, total = _recipe_time_values(recipe)
        servings = recipe.servings or profile.servings
        with st.container(border=True):
            st.markdown(f"## {index}. {sentence_case(recipe.title)}")
            if recipe.description:
                st.write(clean_user_text(recipe.description))

            st.markdown("### Información de la receta")
            info_lines = [
                f"**Tiempo de preparación:** {prep} minutos",
                f"**Tiempo de cocinado:** {cook} minutos",
                f"**Tiempo total:** {total} minutos",
                f"**Raciones:** {servings}",
            ]
            if recipe.category:
                info_lines.append(f"**Categoría:** {clean_user_text(recipe.category).lower()}")
            if recipe.cuisine:
                info_lines.append(f"**Tipo de cocina:** {clean_user_text(recipe.cuisine).lower()}")
            if recipe.calories_per_serving:
                info_lines.append(f"**Calorías por ración:** {recipe.calories_per_serving} kcal")
            for line in info_lines:
                st.markdown(f"- {line}")

            st.markdown("### Ingredientes")
            for ingredient in recipe.ingredients_used:
                st.markdown(f"- {sentence_case(ingredient)}")

            if recipe.shopping_list:
                with st.expander("Opcional para completar la receta", expanded=False):
                    for item in recipe.shopping_list:
                        st.write(f"• {sentence_case(item)}")

            st.markdown("### Cómo prepararlo paso a paso")
            for step_index, step in enumerate(recipe.steps, 1):
                st.markdown(f"**{step_index}.** {clean_user_text(step)}")

            if recipe.anti_waste_tip:
                st.caption("Consejo de aprovechamiento: " + clean_user_text(recipe.anti_waste_tip))

            if recipe.allergen_alerts:
                st.warning("Revisa esto antes de cocinar: " + "; ".join(clean_user_text(note) for note in recipe.allergen_alerts))

            recipe_image = _decode_recipe_image(recipe) if show_images else None
            if recipe_image:
                st.markdown("### Imagen de la receta")
                st.image(recipe_image, caption="Imagen generada para esta receta", use_container_width=True)
            elif show_images and getattr(recipe, "image_generation_error", ""):
                st.caption(clean_user_text(recipe.image_generation_error))


def analyze_current_inputs(
    manual_text: str,
    profile: UserProfile,
    remember_fridge: bool,
    update_mode: UpdateMode,
    confirm_replace: bool,
    prepared_images: list[PreparedImageInput] | None = None,
    no_food_message: str | None = None,
) -> ActionResult:
    """Analyze every prepared input before applying one atomic inventory update."""
    validate_profile_preferences(profile)
    parse_result = parse_manual_ingredients(manual_text)
    images = list(prepared_images or [])

    if not manual_text.strip() and not images:
        if remember_fridge and get_inventory():
            return None, None, parse_result
        raise UserFacingError(
            no_food_message
            or "No hay texto ni fotos preparados. Escribe algún alimento o añade una foto para empezar."
        )

    if manual_text.strip() and not parse_result.accepted_items and not images:
        if not parse_result.used_agent:
            raise UserFacingError(
                "No he podido conectar con el agente de IA que entiende los alimentos. "
                "El texto parece válido, pero ahora mismo no puedo revisarlo con Gemini."
            )
        raise UserFacingError(
            "No he encontrado alimentos claros en el texto. "
            "Escribe alimentos concretos, con cantidades si las conoces, y vuelve a intentarlo."
        )

    image_results: list[tuple[str, FridgeAnalysis]] = []
    for prepared_image in images:
        validate_image_upload(
            prepared_image.image_bytes,
            prepared_image.mime_type,
            settings.max_image_mb,
        )
        try:
            image_analysis = analyze_image_bytes(
                prepared_image.image_bytes,
                prepared_image.mime_type,
            )
        except ImageValidationError:
            raise
        except Exception as exc:
            raise UserFacingError(
                f"No he podido analizar {prepared_image.caption.lower()}. "
                "No he cambiado la nevera guardada. Vuelve a intentarlo en unos segundos."
            ) from exc
        image_results.append((prepared_image.source, image_analysis))

    incoming_items = build_incoming_inventory(
        parse_result.accepted_items,
        image_results,
    )
    if not incoming_items:
        unchanged_message = (
            "Mantengo la nevera guardada tal como estaba."
            if remember_fridge and get_inventory()
            else "No se ha guardado ningún cambio."
        )
        if manual_text.strip() and images:
            message = (
                "No he encontrado alimentos ni en el texto ni en las fotos preparadas. "
                + unchanged_message
            )
        elif images:
            message = (
                "No he encontrado alimentos claros en las fotos preparadas. "
                + unchanged_message
            )
        elif not parse_result.used_agent:
            message = (
                "No he podido conectar con el agente de IA que entiende los alimentos. "
                + unchanged_message
            )
        else:
            message = "No he encontrado alimentos claros en el texto. " + unchanged_message
        raise UserFacingError(message)

    analysis = merge_fridge_analyses(result for _, result in image_results)
    update_result = None
    if remember_fridge:
        existing_inventory = get_inventory()
        update_result = apply_inventory_update(existing_inventory, incoming_items, update_mode)
        set_inventory(update_result.inventory, persist=True)
        st.session_state["clear_consumed_inputs"] = True
        session_id = save_session_if_allowed(
            {
                "event": "inventory_update",
                "update_mode": update_mode,
                "input_sources": [
                    *(("manual",) if parse_result.accepted_items else ()),
                    *(source for source, _ in image_results),
                ],
                "fridge_inventory": [item.model_dump() for item in update_result.inventory],
            },
            allow_save=True,
        )
        if session_id:
            st.session_state["last_inventory_session_id"] = session_id
    else:
        update_result = InventoryUpdateResult(
            inventory=incoming_items,
            added=[item.name for item in incoming_items],
            mode="replace",
        )

    st.session_state["last_analysis"] = analysis.model_dump() if analysis else None
    st.session_state["last_update"] = update_result.model_dump() if update_result else None
    return analysis, update_result, parse_result


def generate_recipes_from_current_inventory(
    profile: UserProfile,
    fallback_inventory: list[InventoryItem] | None = None,
    use_saved_inventory: bool = True,
    generate_images: bool = True,
    image_progress_callback: Callable[[int, int, bool], None] | None = None,
) -> RecipeResponse:
    """Generate recipes from the saved inventory or from the latest temporary analysis."""
    inventory = (get_inventory() if use_saved_inventory else []) or fallback_inventory or []
    ingredients = inventory_to_recipe_ingredients(inventory)
    if not ingredients:
        raise UserFacingError("No tengo ingredientes suficientes para generar recetas. Analiza la nevera o escribe alimentos primero.")
    response = generate_recipes(ingredients, profile, fridge_analysis=None)
    return attach_recipe_images(
        response,
        profile,
        enabled=generate_images,
        progress_callback=image_progress_callback,
    )


def run_action_with_status(label: str, steps: list[str], action: Callable) -> object | None:
    """Run an action with progress and show validation messages outside it.

    Validation problems should not be hidden inside the status box. The status
    tells the user that the process stopped, while the actual instruction is
    rendered below the box as a normal warning/error that is easier to notice on
    desktop and mobile.
    """
    user_message = ""
    message_kind = "warning"
    preference_issues: list[str] = []

    with st.status(label, expanded=True) as status:
        try:
            for step in steps[:-1]:
                status.write(t(step))
            result = action(status)
            status.write(t(steps[-1]))
            status.update(label=t("Listo"), state="complete", expanded=False)
            return result
        except UserFacingError as exc:
            status.update(label=t("No se ha completado la acción"), state="error", expanded=False)
            user_message = str(exc)
            message_kind = "warning"
        except ImageValidationError as exc:
            status.update(label=t("No he podido leer la imagen"), state="error", expanded=False)
            user_message = str(exc)
            message_kind = "error"
        except PreferenceValidationError as exc:
            status.update(label=t("Revisa tus preferencias"), state="error", expanded=False)
            preference_issues = [issue.message for issue in exc.issues]
            message_kind = "warning"
        except Exception:
            status.update(label=t("No he podido terminar la operación"), state="error", expanded=False)
            user_message = "Ha ocurrido un problema inesperado. Revisa la entrada y vuelve a intentarlo en unos segundos."
            message_kind = "error"

    if preference_issues:
        for issue in preference_issues:
            st.warning(issue)
    elif user_message:
        if message_kind == "error":
            st.error(user_message)
        else:
            st.warning(user_message)
    return None


init_state()
reset_consumed_inputs_if_needed()
install_streamlit_i18n(st, current_language)
selected_visual_theme = render_theme_selector()
apply_app_style()
st.markdown(build_theme_css(selected_visual_theme), unsafe_allow_html=True)
render_language_selector()
profile, remember_fridge, update_mode, generate_recipe_images = build_profile()
show_hero()
show_fridge_question_box(remember_fridge)
if remember_fridge:
    show_inventory(
        get_inventory(),
        title="Alimentos guardados",
        editable=True,
        widget_namespace="saved_inventory_top",
    )
    show_inventory_action_message()

st.header("1. Entrada")
if remember_fridge:
    soft_note = (
        _html_text("Antes de añadir información, revisa cómo quieres actualizar tu nevera en el panel lateral.")
        + " "
        + _html_text("Usa")
        + " <strong>"
        + _html_text("Sustituir")
        + "</strong> "
        + _html_text("para una foto o lista completa, y")
        + " <strong>"
        + _html_text("Añadir")
        + "</strong> "
        + _html_text("para una parte concreta como un cajón.")
    )
    st.markdown(f"<div class='soft-note'>{soft_note}</div>", unsafe_allow_html=True)

available_tabs = ["Formulario", "Subir foto"]
if can_offer_device_camera():
    available_tabs.append("Cámara del dispositivo")
available_tabs.append("Cámara interna")

tabs = st.tabs(available_tabs)
manual_text = ""

with tabs[0]:
    manual_text = st.text_area(
        "Ingredientes manuales",
        placeholder="Ejemplo: huevos, arroz, tomate, calabacín, queso",
        help=(
            "Puedes mezclar frases normales con ingredientes. La app separará los alimentos "
            "y descartará lo que no sirva para la nevera."
        ),
        key=f"manual_ingredients_{st.session_state.get('manual_input_version', 0)}",
    )
    if manual_text.strip():
        st.caption(
            "Revisaré el texto al pulsar Analizar nevera o Generar recetas para evitar "
            "llamadas innecesarias mientras escribes."
        )

with tabs[1]:
    uploaded = st.file_uploader(
        "Sube una foto de alimentos (JPG, PNG o WEBP)",
        type=["jpg", "jpeg", "png", "webp"],
        key=f"fridge_upload_{st.session_state.get('upload_widget_version', 0)}",
        max_upload_size=settings.max_image_mb,
    )
    if uploaded:
        image_bytes = uploaded.getvalue()
        mime_type = uploaded.type or mimetypes.guess_type(uploaded.name)[0] or "image/jpeg"
        validate_image_upload(image_bytes, mime_type, settings.max_image_mb)
        store_prepared_image(image_bytes, mime_type, "Foto subida", "upload")

    upload_image = get_prepared_image("upload")
    if upload_image:
        st.image(upload_image.image_bytes, caption="Foto preparada", use_container_width=True)
        if st.button("Quitar foto subida", key="clear_upload_photo", use_container_width=True):
            clear_prepared_image("upload")
            st.rerun()

current_tab_index = 2
if "Cámara del dispositivo" in available_tabs:
    with tabs[current_tab_index]:
        st.write("Haz una foto de la nevera o de los alimentos directamente desde este dispositivo.")
        st.caption(
            "La cámara trasera se abre de forma predeterminada. "
            "Puedes cambiar de cámara cuando el dispositivo disponga de más de una."
        )
        try:
            device_capture = rear_camera_input(
                key="device_camera_rear",
                max_image_mb=settings.max_image_mb,
                preferred_facing_mode="environment",
                capture_label=t("Hacer foto"),
                switch_label=t("Cambiar cámara"),
                starting_label=t("Abriendo la cámara trasera…"),
            )
        except Exception:
            device_capture = None
            st.warning(
                "No he podido preparar la cámara de este dispositivo. "
                "Puedes continuar desde la pestaña Subir foto."
            )

        if device_capture:
            previous_capture_id = st.session_state.get("last_device_camera_capture_id")
            if device_capture.capture_id != previous_capture_id:
                try:
                    validate_image_upload(
                        device_capture.image_bytes,
                        device_capture.mime_type,
                        settings.max_image_mb,
                    )
                    store_prepared_image(
                        device_capture.image_bytes,
                        device_capture.mime_type,
                        "Foto del dispositivo",
                        "device_camera",
                    )
                    st.session_state["last_device_camera_capture_id"] = device_capture.capture_id
                    st.success("Foto realizada correctamente.")
                except ImageValidationError as exc:
                    st.error(str(exc))
                except Exception:
                    st.error(
                        "No he podido preparar la foto realizada. "
                        "Vuelve a intentarlo o usa la pestaña Subir foto."
                    )

        device_image = get_prepared_image("device_camera")
        if device_image:
            st.image(device_image.image_bytes, caption="Foto preparada", use_container_width=True)
            if st.button(
                "Quitar foto del dispositivo",
                key="clear_device_photo",
                use_container_width=True,
            ):
                clear_prepared_image("device_camera")
                st.rerun()
    current_tab_index += 1

with tabs[current_tab_index]:
    st.write("Asegúrate de tener conectada una cámara dentro de la nevera para poder usar esta opción.")
    if st.button("Hacer foto con cámara interna"):
        capture_internal_camera_with_feedback()

    internal_image = get_prepared_image("internal_camera")
    if internal_image:
        st.image(internal_image.image_bytes, caption="Foto preparada", use_container_width=True)
        if st.button(
            "Quitar foto de la cámara interna",
            key="clear_internal_photo",
            use_container_width=True,
        ):
            clear_prepared_image("internal_camera")
            st.rerun()

prepared_images = get_prepared_images()
if prepared_images:
    prepared_labels = ", ".join(image.caption for image in prepared_images)
    st.caption(f"Entradas de imagen preparadas: {prepared_labels}")

confirm_replace = False

st.header("2. Resultado")
if remember_fridge:
    st.markdown(
        """
        <style>
            div[data-testid="column"]:nth-of-type(3) div.stButton > button {
                border: 1px solid rgba(217, 131, 36, 0.35);
                background: #fff7ed;
                color: #7c3d00;
            }
            div[data-testid="column"]:nth-of-type(3) div.stButton > button:hover {
                border-color: rgba(217, 131, 36, 0.7);
                background: #fff1dc;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

button_columns = st.columns([1, 1, 1])
with button_columns[0]:
    analyze_clicked = st.button("🔎 Analizar nevera", type="primary", use_container_width=True)

if remember_fridge:
    with button_columns[1]:
        recipes_clicked = st.button("🍳 Generar recetas", type="secondary", use_container_width=True)
    with button_columns[2]:
        clear_clicked = st.button("🧹 Vaciar nevera guardada", type="secondary", use_container_width=True)
else:
    clear_clicked = False
    with button_columns[2]:
        recipes_clicked = st.button("🍳 Generar recetas", type="secondary", use_container_width=True)

if clear_clicked:
    show_clear_inventory_dialog(remember_fridge)

if st.session_state.get("inventory_clear_message"):
    clear_message = _html_text(st.session_state["inventory_clear_message"])
    st.markdown(f"<div class='danger-soft'>{clear_message}</div>", unsafe_allow_html=True)
    st.session_state["inventory_clear_message"] = ""

has_available_input = bool(manual_text.strip() or prepared_images or (remember_fridge and get_inventory()))

if analyze_clicked:
    if not has_available_input:
        st.warning("No he encontrado alimentos que analizar. Escribe al menos un alimento o sube una foto para empezar.")
    else:
        result = run_action_with_status(
            "Analizando tu nevera",
            [
                "Entendiendo el texto que has escrito, si lo hay.",
                "Revisando todas las fotos que has preparado.",
                "Separando alimentos reales de texto que no corresponde a la nevera.",
                "Revisión terminada.",
            ],
            lambda status: analyze_current_inputs(
                manual_text,
                profile,
                remember_fridge,
                update_mode,
                confirm_replace,
                prepared_images,
                "No he encontrado alimentos que analizar. Escribe al menos un alimento claro o sube una foto para empezar.",
            ),
        )
        if result:
            _, update_result, parse_result = result
            show_manual_feedback(parse_result)
            if update_result:
                show_inventory_update(update_result)
                show_inventory(update_result.inventory, title="Alimentos detectados")
            elif remember_fridge and get_inventory():
                st.info("No se han introducido alimentos nuevos. Mantengo la nevera guardada tal como estaba.")
                show_inventory(
                    get_inventory(),
                    title="Alimentos guardados actualmente",
                    editable=True,
                    widget_namespace="saved_inventory_analysis_result",
                )

if recipes_clicked:
    if not has_available_input:
        st.warning("No es posible generar recetas si no se ha introducido ningún alimento. Escribe ingredientes o sube una foto y vuelve a intentarlo.")
    else:
        def _generate(status):
            analysis, update_result, parse_result = analyze_current_inputs(
                manual_text,
                profile,
                remember_fridge,
                update_mode,
                confirm_replace,
                prepared_images,
                "No es posible generar recetas si no se ha introducido ningún alimento. Escribe ingredientes o sube una foto y vuelve a intentarlo.",
            )
            status.write(t("Creando recetas con los alimentos disponibles."))
            if generate_recipe_images:
                status.write(t("Generando también las imágenes de las recetas."))
            inventory = get_inventory() if remember_fridge else (update_result.inventory if update_result else [])
            validated_profile = validate_profile_preferences(profile)

            def _image_progress(current: int, total: int, cache_hit: bool) -> None:
                if not generate_recipe_images:
                    return
                status.write(t(f"Imagen {current} de {total}: preparando la imagen de la receta."))

            response = generate_recipes_from_current_inventory(
                validated_profile,
                inventory,
                use_saved_inventory=remember_fridge,
                generate_images=generate_recipe_images,
                image_progress_callback=_image_progress,
            )
            st.session_state["last_recipes"] = response.model_dump()
            return parse_result, update_result, response

        recipe_steps = [
            "Revisando los alimentos disponibles.",
            "Guardando los alimentos de tu nevera.",
            "Comprobando qué recetas se pueden preparar.",
            "Buscando recetas variadas, realistas y fáciles de seguir.",
        ]
        if generate_recipe_images:
            recipe_steps.append("Preparando una imagen para cada receta.")
        recipe_steps.append("¡Tus recetas ya están listas!")

        result = run_action_with_status(
            "Generando recetas",
            recipe_steps,
            _generate,
        )
        if result:
            parse_result, update_result, response = result
            show_manual_feedback(parse_result)
            if update_result and remember_fridge:
                show_inventory_update(update_result)
            show_recipes(response, profile, show_images=generate_recipe_images)
