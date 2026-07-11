from __future__ import annotations

import mimetypes
import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from src.fridgechef.blink_camera import capture_blink_photo_sync
from src.fridgechef.config import get_settings
from src.fridgechef.models import FridgeAnalysis, PipelineResult, UserProfile
from src.fridgechef.pipeline import FridgeChefPipeline
from src.fridgechef.security import ImageValidationError

settings = get_settings()

st.set_page_config(page_title="FridgeChef AI", page_icon="🍽️", layout="wide")

st.markdown(
    """
    <style>
    .main .block-container {max-width: 1120px; padding-top: 1rem;}
    .stButton>button {width: 100%; border-radius: 12px; font-weight: 600;}
    .friendly-box {border: 1px solid #e5e7eb; border-radius: 14px; padding: 1rem; background: #ffffff;}
    .small-muted {color: #6b7280; font-size: 0.92rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


def split_manual_ingredients(text: str) -> list[str]:
    """Convert comma/newline separated text into a clean ingredient list."""
    return [item.strip() for item in text.replace("\n", ",").split(",") if item.strip()]




def store_current_image(image_data: bytes, image_mime_type: str, caption: str) -> None:
    """Persist the selected image in Streamlit session state across reruns."""
    st.session_state["current_image_bytes"] = image_data
    st.session_state["current_image_mime_type"] = image_mime_type
    st.session_state["current_image_caption"] = caption


def get_current_image() -> tuple[bytes | None, str]:
    """Return the latest image selected by the user during the current session."""
    return (
        st.session_state.get("current_image_bytes"),
        st.session_state.get("current_image_mime_type", "image/jpeg"),
    )


def show_recognized_items(items: list[str]) -> None:
    """Render recognized ingredients in a friendly way."""
    if not items:
        st.info("Todavía no he reconocido ingredientes claros.")
        return

    st.markdown("**He reconocido esto:**")
    st.write(", ".join(items))


def show_image_summary(analysis: FridgeAnalysis | None, recognized_items: list[str]) -> None:
    """Display a human-friendly image summary and keep technical JSON optional."""
    if not analysis and not recognized_items:
        return

    st.subheader("Lo que he visto")
    show_recognized_items(recognized_items)

    if analysis and analysis.possible_spoiled_items:
        st.warning("Hay algún alimento que podría estar en mal estado. Revísalo antes de usarlo.")
        for item in analysis.possible_spoiled_items:
            st.write(f"- {item.name}: {item.evidence or 'posible señal visual dudosa'}")

    if analysis and analysis.uncertain_items:
        with st.expander("Elementos que no se ven del todo claros"):
            for item in analysis.uncertain_items:
                st.write(f"- {item}")

    if analysis:
        with st.expander("Detalle técnico del análisis de imagen"):
            st.json(analysis.model_dump())


def show_no_recipe_message(result: PipelineResult) -> None:
    """Explain why recipes were not generated without exposing technical details."""
    st.warning(result.recipe_response.no_recipe_reason or result.recipe_response.global_explanation)
    show_recognized_items(result.recipe_response.recognized_ingredients)
    st.info(
        "Puedes subir otra foto con más alimentos visibles o escribir ingredientes manualmente. "
        "La aplicación prefiere no inventar recetas cuando no tiene una base fiable."
    )


def show_recipes(result: PipelineResult) -> None:
    """Render recipe cards returned by the pipeline."""
    for index, recipe in enumerate(result.recipe_response.recipes, 1):
        with st.expander(f"{index}. {recipe.title} · {recipe.time_min} min", expanded=index == 1):
            st.write(recipe.description)

            st.markdown("**Por qué encaja**")
            st.write(recipe.why_this_recipe)

            st.markdown("**Ingredientes usados**")
            st.write(", ".join(recipe.ingredients_used) if recipe.ingredients_used else "No hay ingredientes suficientes.")

            if recipe.missing_required_for_target:
                st.markdown("**Faltaría para la receta concreta**")
                st.write(", ".join(recipe.missing_required_for_target))

            st.markdown("**Pasos**")
            for step in recipe.steps:
                st.write(f"- {step}")

            st.markdown("**Consejo para aprovechar comida**")
            st.write(recipe.anti_waste_tip)

            if recipe.nutrition_notes:
                st.markdown("**Notas nutricionales**")
                for note in recipe.nutrition_notes:
                    st.write(f"- {note}")

            if recipe.shopping_list:
                st.markdown("**Si quieres completar la receta, podrías comprar**")
                st.write(", ".join(recipe.shopping_list))


def build_profile() -> UserProfile:
    """Collect sidebar values and build the profile consumed by the pipeline."""
    with st.sidebar:
        st.header("Perfil y preferencias")
        diet = st.multiselect(
            "Dieta",
            ["vegetariana", "vegana", "sin lactosa", "sin gluten", "halal", "alta en proteína", "mediterránea"],
        )
        allergies = st.multiselect(
            "Alergias",
            ["huevo", "leche", "gluten", "frutos secos", "cacahuete", "marisco", "pescado", "soja"],
        )
        intolerances = st.multiselect("Intolerancias", ["lactosa", "gluten", "fructosa", "sorbitol"])
        dislikes = st.multiselect("No me gusta", ["cebolla", "ajo", "pimiento", "setas", "picante", "queso", "tomate"])
        goals = st.multiselect(
            "Objetivo",
            [
                "comida rápida",
                "comida económica",
                "pérdida de peso",
                "ganar masa muscular",
                "meal prep",
                "cena ligera",
                "aprovechar sobras",
            ],
        )
        time_limit_min = st.slider("Tiempo máximo", 10, 90, 30, step=5)
        servings = st.slider("Raciones", 1, 8, 2)
        wants_target_recipe = st.toggle("Quiero hacer una receta concreta", value=False)
        target_recipe = st.text_input("Receta concreta", placeholder="Ejemplo: tortilla de patatas") if wants_target_recipe else ""
        extra_context = st.text_area(
            "Contexto adicional",
            placeholder="Ejemplo: hoy he entrenado y quiero algo sencillo con proteína.",
        )

        with st.expander("Opciones avanzadas"):
            allow_save_session = st.toggle("Guardar resultado de forma opcional", value=False)
            allow_save_image = st.toggle("Guardar imagen de forma opcional", value=False)

    st.session_state["allow_save_session"] = allow_save_session
    st.session_state["allow_save_image"] = allow_save_image

    return UserProfile(
        diet=diet,
        allergies=allergies,
        intolerances=intolerances,
        dislikes=dislikes,
        goals=goals,
        time_limit_min=time_limit_min,
        servings=servings,
        wants_target_recipe=wants_target_recipe,
        target_recipe=target_recipe,
        extra_context=extra_context,
    )


profile = build_profile()

st.title("🍽️ FridgeChef AI")
st.caption("Analiza lo que hay en la nevera y propone recetas realistas sin inventar ingredientes.")

st.header("1. Entrada")
tab_text, tab_upload, tab_device_camera, tab_internal_camera = st.tabs(
    ["Formulario", "Subir foto", "Cámara del dispositivo", "Cámara Interna"]
)

image_bytes, mime_type = get_current_image()
manual_text = ""

with tab_text:
    manual_text = st.text_area(
        "Ingredientes manuales",
        placeholder="Ejemplo: huevos, arroz, tomate, calabacín, queso",
    )

with tab_upload:
    uploaded = st.file_uploader("Sube una imagen JPG, PNG o WEBP", type=["jpg", "jpeg", "png", "webp"])
    if uploaded:
        image_bytes = uploaded.getvalue()
        mime_type = uploaded.type or mimetypes.guess_type(uploaded.name)[0] or "image/jpeg"
        store_current_image(image_bytes, mime_type, "Imagen subida")
        st.image(image_bytes, caption="Imagen subida", use_container_width=True)

with tab_device_camera:
    camera_img = st.camera_input("Haz una foto desde el navegador o el móvil")
    if camera_img:
        image_bytes = camera_img.getvalue()
        mime_type = camera_img.type or "image/jpeg"
        store_current_image(image_bytes, mime_type, "Foto tomada")
        st.image(image_bytes, caption="Foto tomada", use_container_width=True)

with tab_internal_camera:
    st.write("Usa esta opción cuando la cámara interna esté preparada para tomar una foto de la nevera.")
    if st.button("Tomar foto con Cámara Interna"):
        try:
            output = capture_blink_photo_sync(
                settings.blink_auth_file,
                settings.blink_output_file,
                settings.blink_max_stale_seconds,
            )
            image_bytes = Path(output).read_bytes()
            mime_type = "image/jpeg"
            store_current_image(image_bytes, mime_type, "Foto de Cámara Interna")
            st.success("Foto tomada correctamente.")
            st.image(image_bytes, caption="Foto de Cámara Interna", use_container_width=True)
        except Exception as exc:
            st.error("No he podido tomar la foto. Revisa que la cámara esté encendida y vuelve a intentarlo.")
            with st.expander("Detalle técnico"):
                st.exception(exc)

manual_ingredients = split_manual_ingredients(manual_text)
image_bytes, mime_type = get_current_image()

if image_bytes and not uploaded and not camera_img:
    st.caption(f"Imagen preparada: {st.session_state.get('current_image_caption', 'imagen seleccionada')}")

st.header("2. Resultado")
if st.button("Analizar nevera y generar recetas", type="primary"):
    if not manual_ingredients and not image_bytes:
        st.error("Añade ingredientes manualmente o sube una foto antes de analizar la nevera.")
        st.stop()

    try:
        progress_box = st.empty()
        with st.status("Preparando el análisis...", expanded=True) as status:
            def progress(message: str) -> None:
                progress_box.info(message)
                status.write(message)

            result = FridgeChefPipeline().run(
                manual_ingredients=manual_ingredients,
                profile=profile,
                image_bytes=image_bytes,
                mime_type=mime_type,
                allow_save_session=st.session_state.get("allow_save_session", False),
                allow_save_image=st.session_state.get("allow_save_image", False),
                progress_callback=progress,
            )
            status.update(label="Análisis terminado", state="complete")

        progress_box.empty()

        show_image_summary(result.fridge_analysis, result.recipe_response.recognized_ingredients)

        if result.warnings:
            st.subheader("Avisos importantes")
            for warning in result.warnings:
                st.warning(warning)

        if result.recipe_response.safety_notes:
            with st.expander("Revisión de seguridad y coherencia"):
                for note in result.recipe_response.safety_notes:
                    st.write(f"- {note}")

        if not result.recipe_response.recipes:
            show_no_recipe_message(result)
        else:
            st.subheader("Recetas propuestas")
            show_recipes(result)
            st.subheader("Resumen")
            st.write(result.recipe_response.global_explanation)

        if result.persisted_session_id:
            st.success("Resultado guardado correctamente.")
        if result.persisted_image_uri:
            st.success("Imagen guardada correctamente.")

    except ImageValidationError as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(
            "No he podido completar el análisis. Puede ser un problema temporal de conexión, credenciales o permisos del proyecto. "
            "Revisa la ventana de terminal y vuelve a intentarlo."
        )
        with st.expander("Detalle técnico"):
            st.exception(exc)
