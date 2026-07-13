from __future__ import annotations

from google.genai import types

from src.fridgechef.config import get_settings
from src.fridgechef.json_utils import extract_json_object
from src.fridgechef.llm_client import get_client
from src.fridgechef.models import FridgeAnalysis
from src.fridgechef.security import validate_image_upload
from src.fridgechef.spanish_guard import ensure_fridge_analysis_spanish

VISION_PROMPT = """
Eres el agente visual de FridgeChef AI Assistant.
Analiza una imagen de nevera, despensa, alimento o producto y devuelve solo JSON válido.

Reglas de detección:
- Detecta únicamente elementos visibles y razonablemente claros.
- No inventes alimentos, cantidades, fechas ni marcas.
- Si algo no está claro, colócalo en uncertain_items en lugar de adivinar.
- Si un elemento parece estar en mal estado, marca el estado adecuado y explica la evidencia visual.
- Nunca confirmes seguridad alimentaria solo a partir de una imagen.
- Todos los textos visibles del JSON deben estar en español de España.
- Deja barcode_observations vacío si no se ve ninguna etiqueta, fecha o código legible.

Required JSON shape:
{
  "visible_ingredients": [
    {"name":"string","quantity_estimate":"string or null","state":"fresh|aging|possible_spoiled|unknown","confidence":0.0,"evidence":"string or null"}
  ],
  "possible_spoiled_items": [
    {"name":"string","quantity_estimate":"string or null","state":"possible_spoiled","confidence":0.0,"evidence":"string or null"}
  ],
  "uncertain_items": ["string"],
  "barcode_observations": [
    {"barcode_text":"string or null","expiry_text":"string or null","product_name_guess":"string or null","confidence":0.0,"notes":["string"]}
  ],
  "notes": ["string"]
}
"""


def analyze_image_bytes(image_bytes: bytes, mime_type: str) -> FridgeAnalysis:
    """Validate an uploaded image and ask Gemini Vision for a structured analysis."""
    settings = get_settings()
    validate_image_upload(image_bytes, mime_type, settings.max_image_mb)

    client = get_client()
    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

    response = client.models.generate_content(
        model=settings.model_name,
        contents=[VISION_PROMPT, image_part],
        config=types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json"),
    )

    data = extract_json_object(response.text)
    analysis = FridgeAnalysis.model_validate(data)
    return ensure_fridge_analysis_spanish(analysis)
