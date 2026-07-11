from __future__ import annotations

from google.genai import types

from src.fridgechef.config import get_settings
from src.fridgechef.json_utils import extract_json_object
from src.fridgechef.llm_client import get_client
from src.fridgechef.models import FridgeAnalysis
from src.fridgechef.security import validate_image_upload

VISION_PROMPT = """
You are the vision component of FridgeChef AI.
Analyze a fridge, shelf or food photo and return only valid JSON.

Detection rules:
- Detect only food items that are clearly visible.
- Do not invent ingredients.
- If the image mainly contains water bottles, bottles, packaging or unidentified liquids, report them exactly as such.
- If something is unclear, place it in uncertain_items instead of guessing.
- If an item may be spoiled, mark it as possible_spoiled and explain the visual evidence.
- Never confirm food safety from an image alone.
- Use short, friendly Spanish names for detected items when possible.
- Leave barcode_observations empty when no readable label, date or barcode is visible.

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
    return FridgeAnalysis.model_validate(data)
