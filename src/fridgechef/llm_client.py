from __future__ import annotations

import os
from pathlib import Path

from src.fridgechef.config import get_settings

try:
    from google import genai
except Exception:  # pragma: no cover - useful for local tests without cloud SDKs
    genai = None

try:
    from google.oauth2 import service_account
except Exception:  # pragma: no cover - useful for local tests without google-auth
    service_account = None


_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def get_client(location: str | None = None):
    """Create a Vertex AI client using the current project settings.

    In local Windows development, Application Default Credentials can resolve the
    service-account JSON implicitly. In Docker on the NAS, the JSON is mounted at
    runtime, so loading it explicitly avoids environment-dependent ADC failures.
    """
    if genai is None:
        raise RuntimeError("La librería google-genai no está instalada en este entorno.")

    settings = get_settings()
    if not settings.project_id:
        raise RuntimeError(
            "No encuentro el proyecto de Google Cloud. Revisa GOOGLE_CLOUD_PROJECT, PROJECT_ID o credentials.json."
        )

    credentials = None
    credentials_path = Path(settings.credentials_path)
    if credentials_path.exists():
        resolved_path = credentials_path.resolve()
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(resolved_path)

        if service_account is None:
            raise RuntimeError("La librería google-auth no está disponible para cargar credentials.json.")

        credentials = service_account.Credentials.from_service_account_file(
            str(resolved_path),
            scopes=[_CLOUD_PLATFORM_SCOPE],
        )
    elif os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        raise RuntimeError(
            f"No existe el fichero de credenciales configurado: {credentials_path}."
        )

    return genai.Client(
        vertexai=True,
        credentials=credentials,
        project=settings.project_id,
        location=location or settings.location,
    )
