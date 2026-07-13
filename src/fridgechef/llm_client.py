from __future__ import annotations

from src.fridgechef.config import get_settings

try:
    from google import genai
except Exception:  # pragma: no cover - useful for local tests without cloud SDKs
    genai = None


def get_client():
    """Create a Vertex AI Gemini client using the current project settings."""
    if genai is None:
        raise RuntimeError("La librería google-genai no está instalada en este entorno.")

    settings = get_settings()
    if not settings.project_id:
        raise RuntimeError(
            "No encuentro el proyecto de Google Cloud. Revisa GOOGLE_CLOUD_PROJECT, PROJECT_ID o credentials.json."
        )
    return genai.Client(vertexai=True, project=settings.project_id, location=settings.location)
