from __future__ import annotations

import os
from pathlib import Path

from src.fridgechef.config import get_settings

try:
    from google import genai
except Exception:  # pragma: no cover - useful for local tests without cloud SDKs
    genai = None


def get_client(location: str | None = None):
    """Create a Vertex AI client using the current project settings."""
    if genai is None:
        raise RuntimeError("La librería google-genai no está instalada en este entorno.")

    settings = get_settings()
    if not settings.project_id:
        raise RuntimeError(
            "No encuentro el proyecto de Google Cloud. Revisa GOOGLE_CLOUD_PROJECT, PROJECT_ID o credentials.json."
        )

    # google-genai uses Application Default Credentials under the hood. The .env
    # usually stores a relative path, so make it absolute here before any model
    # call. This avoids confusing failures when Streamlit, ADK or a BAT file runs
    # from a slightly different working directory.
    credentials_path = Path(settings.credentials_path)
    if credentials_path.exists():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credentials_path.resolve())

    return genai.Client(vertexai=True, project=settings.project_id, location=location or settings.location)
