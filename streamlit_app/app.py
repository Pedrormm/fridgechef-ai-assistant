from __future__ import annotations

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
from src.fridgechef.fridge_qa import answer_fridge_question
from src.fridgechef.inventory import (
    apply_inventory_update,
    friendly_state_label,
    inventory_from_inputs,
    inventory_to_recipe_ingredients,
    needs_replace_confirmation,
)
from src.fridgechef.models import FridgeAnalysis, InventoryItem, InventoryUpdateResult, RecipeResponse, UserProfile
from src.fridgechef.persistence import (
    InventoryPersistenceResult,
    clear_inventory_state,
    load_inventory_state,
    save_inventory_state,
    save_session_if_allowed,
)
from src.fridgechef.preferences import PreferenceValidationError, validate_profile_preferences
from src.fridgechef.recipe_planner import clean_user_text, generate_recipes, sentence_case
from src.fridgechef.security import ImageValidationError, validate_image_upload
from src.fridgechef.text_parser import ManualIngredientParseResult, parse_manual_ingredients
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
    defaults = {
        "current_image_bytes": None,
        "current_image_mime_type": "image/jpeg",
        "current_image_caption": "",
        "current_image_source": "upload",
        "fridge_inventory": [],
        "last_analysis": None,
        "last_update": None,
        "last_recipes": None,
        "inventory_clear_message": "",
        "inventory_persistence_backend": "",
        "inventory_persistence_ok": True,
        "inventory_persistence_warning": "",
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
    st.markdown(
        """
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
            .stDeployButton {
                display: none !important;
                visibility: hidden !important;
                height: 0 !important;
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
                z-index: 2147483646 !important;
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
                content: "📷 Seleccionar foto";
                font-size: 0.95rem !important;
                font-weight: 400 !important;
                color: #2d3142 !important;
            }
            [data-testid="stCameraInput"] button::after {
                content: "Hacer foto";
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
                content: "Hasta 200 MB por foto · JPG, PNG o WEBP";
                font-size: 0.86rem !important;
                color: rgba(45, 49, 66, 0.58) !important;
            }
            [data-testid="stFileUploaderDropzone"] > div:last-child::after {
                content: "Arrastra una foto aquí o selecciónala desde tu dispositivo";
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
                content: "Permite el acceso a la cámara para hacer la foto desde este dispositivo.";
                display: block;
                color: rgba(45, 49, 66, 0.74) !important;
                font-size: 1rem !important;
                line-height: 1.45 !important;
            }

            @media (max-width: 768px) {
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
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

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
            st.markdown("### La nevera guardada ya está vacía")
            st.write("Ahora mismo no hay alimentos guardados que borrar.")
            if st.button("Entendido", type="primary", use_container_width=True):
                st.session_state["inventory_clear_message"] = clear_inventory(remember_fridge)
                st.rerun()
            return

        st.markdown("### ¿Quieres vaciar la nevera guardada?")
        st.write(
            "Se eliminará la lista de alimentos que tengo recordada para esta sesión. "
            "No afectará a las fotos ni a los ingredientes que escribas después."
        )
        col_cancel, col_confirm = st.columns(2)
        with col_cancel:
            if st.button("Cancelar", use_container_width=True):
                st.rerun()
        with col_confirm:
            if st.button("Sí, vaciar la lista", type="primary", use_container_width=True):
                st.session_state["inventory_clear_message"] = clear_inventory(remember_fridge)
                st.rerun()

    if hasattr(st, "dialog"):
        @st.dialog("Vaciar nevera guardada")
        def _dialog() -> None:
            _confirm_content()

        _dialog()
    else:  # pragma: no cover - compatibility for older Streamlit versions
        with st.container(border=True):
            _confirm_content()


def store_current_image(image_data: bytes, image_mime_type: str, caption: str, source: InputSource) -> None:
    """Keep the selected image available after Streamlit reruns the script."""
    st.session_state["current_image_bytes"] = image_data
    st.session_state["current_image_mime_type"] = image_mime_type
    st.session_state["current_image_caption"] = caption
    st.session_state["current_image_source"] = source


def get_current_image() -> tuple[bytes | None, str, InputSource]:
    """Return the current image, its MIME type and the input source."""
    return (
        st.session_state.get("current_image_bytes"),
        st.session_state.get("current_image_mime_type", "image/jpeg"),
        st.session_state.get("current_image_source", "upload"),
    )


def capture_internal_camera_with_feedback() -> None:
    """Capture a fresh image from the fridge camera with friendly progress text."""
    with st.status("Conectando con la cámara interna", expanded=True) as status:
        try:
            status.write("Preparando la conexión con la cámara que está dentro de la nevera.")
            status.write("Solicitando una foto nueva para evitar usar una imagen anterior.")
            output = capture_blink_photo_sync(
                settings.blink_auth_file,
                settings.blink_output_file,
                settings.blink_max_stale_seconds,
            )
            status.write("Comprobando que la foto se ha guardado correctamente.")
            image_bytes = Path(output).read_bytes()
            validate_image_upload(image_bytes, "image/jpeg", settings.max_image_mb)
            store_current_image(image_bytes, "image/jpeg", "Foto de cámara interna", "internal_camera")
            status.update(label="Foto realizada", state="complete", expanded=False)
            st.success("Foto realizada correctamente.")
            st.image(image_bytes, caption="Foto preparada", use_container_width=True)
        except Exception as exc:
            status.update(label="No he podido realizar la foto", state="error", expanded=False)
            st.error(
                "No he podido realizar una foto nueva con la cámara interna. "
                "Revisa que esté conectada, con batería o alimentación, y vuelve a intentarlo."
            )
            st.caption(clean_user_text(exc))


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


def optional_multiselect_with_other(
    field_key: str,
    label: str,
    options: list[str],
    placeholder: str,
    other_label: str,
    other_placeholder: str,
) -> tuple[list[str], str | None]:
    """Render a Spanish multi-selector without the native English menu text.

    The native multiselect includes an internal English bulk-selection label that
    cannot be translated reliably from app code. This custom selector keeps the
    same behavior with explicit checkboxes and a compact popover, while the
    semantic validation is still handled later by the dedicated preference agent.
    """
    state_key = f"selected_{field_key}"
    current = list(st.session_state.get(state_key, []))
    summary = placeholder if not current else ", ".join(current[:2]) + ("..." if len(current) > 2 else "")

    # Keep the field name visible even while the compact selector is closed.
    # The selector behavior remains unchanged; this label only restores the
    # explanatory context expected in the preferences panel.
    st.markdown(f"**{label}**")

    if hasattr(st, "popover"):
        container = st.popover(summary, use_container_width=True)
    else:  # pragma: no cover - compatibility for older Streamlit versions
        container = st.expander(summary, expanded=False)

    selected: list[str] = []
    with container:
        st.caption("Puedes elegir una o varias opciones, o dejarlo sin marcar.")
        for option in options:
            checked = st.checkbox(
                option,
                value=option in current,
                key=f"{field_key}_{_selector_key(option)}",
            )
            if checked:
                selected.append(option)
        other_checked = st.checkbox(
            other_label,
            value=other_label in current,
            key=f"{field_key}_{_selector_key(other_label)}",
            help="Elige esta opción solo si quieres escribir una preferencia distinta.",
        )
        if other_checked:
            selected.append(other_label)

    st.session_state[state_key] = selected
    custom_value: str | None = None
    if other_label in selected:
        custom_value = st.text_input(
            f"Especifica {label.lower()}",
            key=f"custom_{field_key}",
            placeholder=other_placeholder,
            help="Escribe una opción clara y relacionada con alimentación o recetas.",
        )
    clean_selected = [value for value in selected if value != other_label]
    return clean_selected, custom_value


def build_profile() -> tuple[UserProfile, bool, UpdateMode]:
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
            elif "firestore" in backend and "sqlite" in backend:
                st.caption("Guardado permanente activo en Firestore y en la base de datos local.")
            elif "firestore" in backend:
                st.caption("Guardado permanente activo en Firestore.")
            else:
                st.caption("Guardado permanente activo en la base de datos local. No necesitas gcloud para usarlo.")

        update_mode: UpdateMode = "replace"
        if remember_fridge:
            update_choice = st.radio(
                "Al añadir alimentos ahora",
                options=["replace", "add"],
                index=0,
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
            ["Vegetariana", "Vegana", "Sin lactosa", "Sin gluten", "Halal", "Alta en proteína", "Mediterránea"],
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
            "No me gusta",
            ["Cebolla", "Ajo", "Pimiento", "Setas", "Picante", "Queso", "Tomate"],
            "No quiero evitar nada por gusto (opcional)",
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
            "Tiempo máximo por receta",
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
        st.caption("Intentaré preparar ese número de recetas, sin forzar opciones poco realistas.")
        wants_target_recipe = st.toggle("Quiero hacer una receta concreta", value=False)
        target_recipe = st.text_input("Receta concreta", placeholder="Ejemplo: tortilla de patatas") if wants_target_recipe else ""
        extra_context = st.text_area(
            "Contexto adicional",
            placeholder="Ejemplo: hoy he entrenado y quiero algo sencillo con proteína.",
        )

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
    return profile, remember_fridge, update_mode


def show_hero() -> None:
    """Render the application title and product-level value proposition."""
    st.markdown(
        """
        <div class="hero-card">
            <h1 style="margin-bottom: 0.25rem;">🍽️ FridgeChef AI Assistant</h1>
            <p class="muted" style="font-size: 1.08rem; margin-bottom: 0;">
                Descubre qué tienes en la nevera, mantén tu inventario al día y convierte tus alimentos
                en ideas de comida sencillas, útiles y personalizadas.
            </p>
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
            f"{sentence_case(item.name)} ({clean_user_text(item.quantity_label)})"
            if item.quantity_label != "Cantidad no indicada"
            else sentence_case(item.name)
            for item in parse_result.accepted_items
        ]
        st.success("Tendré en cuenta: " + ", ".join(names))
    if parse_result.ignored_fragments:
        with st.expander("Texto que no he usado", expanded=False):
            for fragment in parse_result.ignored_fragments:
                st.write(f"• **{clean_user_text(fragment.text)}** — {clean_user_text(fragment.reason)}")


def show_inventory(inventory: list[InventoryItem], title: str = "Alimentos guardados") -> None:
    """Display the fridge inventory as friendly, plain-text cards."""
    st.subheader(title)
    if not inventory:
        st.info("Todavía no hay alimentos guardados. Escribe ingredientes o sube una foto para empezar.")
        return

    columns = st.columns(2)
    for index, item in enumerate(inventory):
        with columns[index % 2]:
            with st.container(border=True):
                st.markdown(f"#### {sentence_case(item.name)}")
                st.write(f"**Cantidad:** {clean_user_text(item.quantity_label)}")
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
        st.markdown("<div class='success-soft'>He actualizado la nevera con lo que acabas de analizar.</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='success-soft'>He añadido los alimentos nuevos sin duplicar los que ya estaban guardados.</div>", unsafe_allow_html=True)

    details = []
    if update_result.added:
        details.append("Añadidos: " + ", ".join(sentence_case(item) for item in update_result.added))
    if update_result.updated:
        details.append("Actualizados: " + ", ".join(sentence_case(item) for item in update_result.updated))
    if update_result.removed:
        details.append("Ya no aparecen: " + ", ".join(sentence_case(item) for item in update_result.removed))
    if details:
        st.caption(" · ".join(details))


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


def show_recipes(response: RecipeResponse, profile: UserProfile) -> None:
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


def analyze_current_inputs(
    manual_text: str,
    profile: UserProfile,
    remember_fridge: bool,
    update_mode: UpdateMode,
    confirm_replace: bool,
    use_prepared_image: bool = True,
) -> ActionResult:
    """Analyze manual text and the current image, then update inventory when enabled."""
    validate_profile_preferences(profile)
    parse_result = parse_manual_ingredients(manual_text)
    image_bytes, mime_type, image_source = get_current_image()
    if not use_prepared_image:
        image_bytes = None

    if manual_text.strip() and not parse_result.accepted_items and not image_bytes:
        raise UserFacingError(
            "No he encontrado alimentos claros en el texto. Escribe alimentos concretos, con cantidades si las conoces, y vuelve a intentarlo."
        )

    analysis = None
    if image_bytes:
        validate_image_upload(image_bytes, mime_type, settings.max_image_mb)
        analysis = analyze_image_bytes(image_bytes, mime_type)

    incoming_items = inventory_from_inputs(
        parse_result.accepted,
        analysis,
        source=image_source,
        manual_items=parse_result.accepted_items,
    )
    if not incoming_items and (not remember_fridge or not get_inventory()):
        raise UserFacingError("Necesito al menos un alimento claro para actualizar la nevera o generar recetas.")

    update_result = None
    if remember_fridge and incoming_items:
        existing_inventory = get_inventory()
        if needs_replace_confirmation(existing_inventory, incoming_items, update_mode) and not confirm_replace:
            raise UserFacingError(
                "Parece que esta entrada tiene muchos menos alimentos que tu nevera guardada. "
                "Si es una foto parcial, elige 'Añadir sin borrar lo anterior'. Si realmente quieres sustituirlo todo, marca la confirmación."
            )
        update_result = apply_inventory_update(existing_inventory, incoming_items, update_mode)
        set_inventory(update_result.inventory, persist=remember_fridge)
        session_id = save_session_if_allowed(
            {
                "event": "inventory_update",
                "update_mode": update_mode,
                "fridge_inventory": [item.model_dump() for item in update_result.inventory],
            },
            allow_save=remember_fridge,
        )
        if session_id:
            st.session_state["last_inventory_session_id"] = session_id
    elif incoming_items:
        update_result = InventoryUpdateResult(inventory=incoming_items, added=[item.name for item in incoming_items], mode="replace")

    st.session_state["last_analysis"] = analysis.model_dump() if analysis else None
    st.session_state["last_update"] = update_result.model_dump() if update_result else None
    return analysis, update_result, parse_result


def generate_recipes_from_current_inventory(
    profile: UserProfile,
    fallback_inventory: list[InventoryItem] | None = None,
    use_saved_inventory: bool = True,
) -> RecipeResponse:
    """Generate recipes from the saved inventory or from the latest temporary analysis."""
    inventory = (get_inventory() if use_saved_inventory else []) or fallback_inventory or []
    ingredients = inventory_to_recipe_ingredients(inventory)
    if not ingredients:
        raise UserFacingError("No tengo ingredientes suficientes para generar recetas. Analiza la nevera o escribe alimentos primero.")
    return generate_recipes(ingredients, profile, fridge_analysis=None)


def run_action_with_status(label: str, steps: list[str], action: Callable) -> object | None:
    """Run a UI action with visible, human-friendly progress messages."""
    with st.status(label, expanded=True) as status:
        try:
            for step in steps[:-1]:
                status.write(step)
            result = action(status)
            status.write(steps[-1])
            status.update(label="Listo", state="complete", expanded=False)
            return result
        except UserFacingError as exc:
            status.update(label="Necesito revisar algo antes de continuar", state="error", expanded=True)
            st.warning(str(exc))
        except ImageValidationError as exc:
            status.update(label="No he podido leer la imagen", state="error", expanded=True)
            st.error(str(exc))
        except PreferenceValidationError as exc:
            status.update(label="Revisa tus preferencias", state="error", expanded=True)
            for issue in exc.issues:
                st.warning(issue.message)
        except Exception:
            status.update(label="No he podido terminar la operación", state="error", expanded=True)
            st.error("Ha ocurrido un problema inesperado. Revisa la entrada y vuelve a intentarlo en unos segundos.")
    return None


init_state()
apply_app_style()
profile, remember_fridge, update_mode = build_profile()
show_hero()
show_fridge_question_box(remember_fridge)
if remember_fridge:
    show_inventory(get_inventory(), title="Alimentos guardados")

st.header("1. Entrada")
if remember_fridge:
    st.markdown(
        "<div class='soft-note'>Antes de añadir información, revisa cómo quieres actualizar tu nevera en el panel lateral. "
        "Usa <strong>Sustituir</strong> para una foto o lista completa, y <strong>Añadir</strong> para una parte concreta como un cajón.</div>",
        unsafe_allow_html=True,
    )

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
        help="Puedes mezclar frases normales con ingredientes. La app separará los alimentos y descartará lo que no sirva para la nevera.",
    )
    if manual_text.strip():
        st.caption("Revisaré el texto al pulsar Analizar nevera o Generar recetas para evitar llamadas innecesarias mientras escribes.")

with tabs[1]:
    uploaded = st.file_uploader("Sube una foto de alimentos (JPG, PNG o WEBP)", type=["jpg", "jpeg", "png", "webp"])
    if uploaded:
        image_bytes = uploaded.getvalue()
        mime_type = uploaded.type or mimetypes.guess_type(uploaded.name)[0] or "image/jpeg"
        store_current_image(image_bytes, mime_type, "Foto subida", "upload")
        st.image(image_bytes, caption="Foto preparada", use_container_width=True)

current_tab_index = 2
if "Cámara del dispositivo" in available_tabs:
    with tabs[current_tab_index]:
        st.write("Haz una foto de la nevera o de los alimentos directamente desde este dispositivo.")
        st.caption("El navegador te pedirá permiso para usar la cámara cuando sea necesario.")
        device_photo = st.camera_input("Hacer foto desde este dispositivo", key="device_camera_photo")
        if device_photo:
            image_bytes = device_photo.getvalue()
            mime_type = device_photo.type or "image/jpeg"
            store_current_image(image_bytes, mime_type, "Foto del dispositivo", "device_camera")
            st.success("Foto realizada correctamente.")
            st.image(image_bytes, caption="Foto preparada", use_container_width=True)
    current_tab_index += 1

with tabs[current_tab_index]:
    st.write("Asegúrate de tener conectada una cámara dentro de la nevera para poder usar esta opción.")
    if st.button("Hacer foto con cámara interna"):
        capture_internal_camera_with_feedback()

    current_internal_image, _, current_internal_source = get_current_image()
    if current_internal_image and current_internal_source == "internal_camera":
        st.image(current_internal_image, caption="Foto preparada", use_container_width=True)

image_bytes, _, _ = get_current_image()
use_prepared_image = bool(image_bytes)
if image_bytes:
    st.caption(f"Imagen preparada: {st.session_state.get('current_image_caption', 'foto seleccionada')}")
    if manual_text.strip():
        use_prepared_image = st.checkbox(
            "También usar la imagen preparada en este análisis",
            value=False,
            help="Déjalo desmarcado si solo quieres analizar los ingredientes que acabas de escribir.",
        )

confirm_replace = False
if remember_fridge and update_mode == "replace" and get_inventory():
    confirm_replace = st.checkbox(
        "Confirmo que esta entrada representa la nevera completa y sustituye lo que había anteriormente",
        value=False,
        help="Solo es necesario marcarlo cuando la nueva entrada parece mucho más pequeña que el inventario guardado.",
    )

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
    st.markdown(f"<div class='danger-soft'>{st.session_state['inventory_clear_message']}</div>", unsafe_allow_html=True)
    st.session_state["inventory_clear_message"] = ""

if analyze_clicked:
    result = run_action_with_status(
        "Analizando tu nevera",
        [
            "Entendiendo el texto que has escrito, si lo hay.",
            "Revisando la foto si hay una imagen preparada.",
            "Separando alimentos reales de texto que no corresponde a la nevera.",
            "Inventario actualizado.",
        ],
        lambda status: analyze_current_inputs(manual_text, profile, remember_fridge, update_mode, confirm_replace, use_prepared_image),
    )
    if result:
        _, update_result, parse_result = result
        show_manual_feedback(parse_result)
        if update_result:
            show_inventory_update(update_result)
            show_inventory(update_result.inventory, title="Alimentos detectados")

if recipes_clicked:
    def _generate(status):
        analysis, update_result, parse_result = analyze_current_inputs(manual_text, profile, remember_fridge, update_mode, confirm_replace, use_prepared_image)
        status.write("Preparando recetas con los alimentos disponibles.")
        inventory = get_inventory() if remember_fridge else (update_result.inventory if update_result else [])
        validated_profile = validate_profile_preferences(profile)
        response = generate_recipes_from_current_inventory(validated_profile, inventory, use_saved_inventory=remember_fridge)
        st.session_state["last_recipes"] = response.model_dump()
        return parse_result, update_result, response

    result = run_action_with_status(
        "Generando recetas",
        [
            "Revisando alimentos escritos o fotografiados.",
            "Actualizando la nevera si has elegido recordarla.",
            "Comprobando si hay alimentos suficientes para cocinar.",
            "Recetas preparadas.",
        ],
        _generate,
    )
    if result:
        parse_result, update_result, response = result
        show_manual_feedback(parse_result)
        if update_result and remember_fridge:
            show_inventory_update(update_result)
        show_recipes(response, profile)
