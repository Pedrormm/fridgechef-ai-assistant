from __future__ import annotations

import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

ROOT = Path.cwd()
if load_dotenv:
    load_dotenv(ROOT / ".env", override=False)

credentials = ROOT / "credentials.json"
if not credentials.exists():
    raise SystemExit("ERROR: credentials.json not found in project root.")

data = json.loads(credentials.read_text(encoding="utf-8"))
project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID") or data.get("project_id")
location = os.getenv("GOOGLE_CLOUD_LOCATION") or "us-central1"
model = os.getenv("VERTEX_MODEL") or "gemini-2.5-flash"

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credentials)
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id or ""
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"

if not project_id:
    raise SystemExit("ERROR: project_id not found in .env or credentials.json.")

print("Testing Gemini with Vertex AI")
print("Project:", project_id)
print("Location:", location)
print("Model:", model)

from google import genai

client = genai.Client(vertexai=True, project=project_id, location=location)
response = client.models.generate_content(
    model=model,
    contents="Say only: OK FridgeChef Gemini works."
)

print("Gemini response:")
print(response.text)
