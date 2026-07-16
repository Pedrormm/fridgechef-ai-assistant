from __future__ import annotations

import os
from pathlib import Path

from src.fridgechef.config import get_settings

try:
    from google import genai
    from google.genai import types as genai_types
except Exception:  # pragma: no cover - useful for local tests without cloud SDKs
    genai = None
    genai_types = None

try:
    from google.oauth2 import service_account
except Exception:  # pragma: no cover - useful for local tests without google-auth
    service_account = None


_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_RETRYABLE_STATUS_CODES = [408, 429, 500, 502, 503, 504]


def get_client(location: str | None = None):
    """Create a resilient Vertex AI client using the current project settings.

    The service-account JSON is loaded explicitly so Docker does not depend on
    machine-specific Application Default Credentials. Production defaults to the
    global endpoint through Settings, and transient capacity errors are retried
    with bounded, jittered exponential backoff.
    """
    if genai is None or genai_types is None:
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

    http_options = genai_types.HttpOptions(
        retry_options=genai_types.HttpRetryOptions(
            initial_delay=1.0,
            attempts=settings.genai_retry_attempts,
            max_delay=16.0,
            exp_base=2.0,
            jitter=1.0,
            http_status_codes=_RETRYABLE_STATUS_CODES,
        ),
        timeout=settings.genai_timeout_ms,
    )

    return genai.Client(
        vertexai=True,
        credentials=credentials,
        project=settings.project_id,
        location=location or settings.location,
        http_options=http_options,
    )
