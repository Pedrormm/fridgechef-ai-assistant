from __future__ import annotations

from google import genai

from src.fridgechef.config import get_settings


def get_client():
    """Create a Vertex AI Gemini client using the current project settings."""
    settings = get_settings()
    if not settings.project_id:
        raise RuntimeError(
            "No encuentro el proyecto de Google Cloud. Revisa GOOGLE_CLOUD_PROJECT, PROJECT_ID o credentials.json."
        )
    return genai.Client(vertexai=True, project=settings.project_id, location=settings.location)
