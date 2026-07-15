from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if load_dotenv and ENV_FILE.exists():
    load_dotenv(ENV_FILE, override=False)

credentials_path = ROOT / "credentials.json"
if not credentials_path.exists():
    raise SystemExit("ERROR: No encuentro credentials.json en la raíz del proyecto.")

credentials_data = json.loads(credentials_path.read_text(encoding="utf-8"))
project_id = (os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID") or credentials_data.get("project_id") or "").strip()
location = (os.getenv("GOOGLE_CLOUD_LOCATION") or "us-central1").strip()
text_model = (os.getenv("VERTEX_MODEL") or "gemini-2.5-flash").strip()
image_model = (os.getenv("VERTEX_IMAGE_MODEL") or "gemini-2.5-flash-image").strip()
image_location = (os.getenv("GOOGLE_CLOUD_IMAGE_LOCATION") or "global").strip()

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credentials_path.resolve())
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"

if not project_id:
    raise SystemExit("ERROR: No se ha resuelto GOOGLE_CLOUD_PROJECT / PROJECT_ID.")

from google import genai

from src.fridgechef.models import RecipeItem, UserProfile
from src.fridgechef.recipe_images import generate_recipe_image

print("FridgeChef - smoke test real de Gemini texto + generación de imagen de receta")
print("Proyecto:", project_id)
print("Región texto:", location)
print("Modelo texto:", text_model)
print("Región imagen:", image_location)
print("Modelo imagen principal:", image_model)

text_client = genai.Client(vertexai=True, project=project_id, location=location)
text_response = text_client.models.generate_content(
    model=text_model,
    contents="Responde únicamente con: OK FridgeChef Gemini funciona.",
)
print("Respuesta de texto:", (text_response.text or "").strip())

recipe = RecipeItem(
    title="Minihamburguesas de cerdo con salsa de tomate y ensalada fresca",
    description="Minihamburguesas caseras de cerdo con salsa de tomate, zanahoria y lechuga.",
    why_this_recipe="Aprovecha carne picada, tomate frito, zanahoria y lechuga.",
    time_min=25,
    prep_time_min=10,
    cook_time_min=15,
    servings=2,
    category="plato principal",
    cuisine="casera",
    ingredients_used=["carne picada de cerdo", "tomate frito", "zanahoria", "lechuga"],
    steps=["Mezcla los ingredientes.", "Cocina la carne.", "Sirve con ensalada."],
    anti_waste_tip="Guarda la zanahoria sobrante rallada.",
)
profile = UserProfile(servings=2, recipe_count=1, time_limit_min=30)
result = generate_recipe_image(recipe, profile, use_cache=False)

if not result.image_base64:
    raise SystemExit("ERROR: No se ha generado imagen. Revisa la traza de error justo encima.")

out_dir = ROOT / "generated" / "smoke_test"
out_dir.mkdir(parents=True, exist_ok=True)
extension = ".jpg" if "jpeg" in (result.image_mime_type or "").lower() else ".png"
out_path = out_dir / f"smoke_test_recipe_image{extension}"
out_path.write_bytes(base64.b64decode(result.image_base64))
print("Imagen generada correctamente en:", out_path)
print("Tamaño de la imagen:", len(base64.b64decode(result.image_base64)), "bytes")
