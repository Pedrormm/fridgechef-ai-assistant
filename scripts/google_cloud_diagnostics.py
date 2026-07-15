from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - dotenv is installed in the project venv
    load_dotenv = None

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"

if load_dotenv and ENV_FILE.exists():
    load_dotenv(ENV_FILE, override=False)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "y", "on", "si", "sí"}


def _resolve_path(raw: str | None, default: str) -> Path:
    value = (raw or default).strip() or default
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _safe_project_from_file(path: Path) -> tuple[dict[str, Any], str, str]:
    if not path.exists():
        raise RuntimeError(f"No encuentro credentials.json en: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"credentials.json no es un JSON válido: {exc}") from exc

    if data.get("type") != "service_account":
        raise RuntimeError("credentials.json no parece una cuenta de servicio.")

    project_id = str(data.get("project_id") or "").strip()
    client_email = str(data.get("client_email") or "").strip()
    private_key = str(data.get("private_key") or "").strip()

    if not project_id or not client_email or not private_key:
        raise RuntimeError("credentials.json no contiene project_id, client_email o private_key.")
    return data, project_id, client_email


def _explain_google_error(exc: BaseException) -> str:
    text = str(exc)
    lower = text.lower()
    if "permission" in lower or "403" in lower:
        return (
            "El JSON existe, pero la cuenta de servicio no tiene permisos suficientes, "
            "la API no está habilitada para ese proyecto o el proyecto del curso ya no está activo."
        )
    if "not found" in lower or "404" in lower:
        return (
            "El proyecto, la región o el modelo no se encuentran. Revisa GOOGLE_CLOUD_PROJECT, "
            "GOOGLE_CLOUD_LOCATION y VERTEX_MODEL."
        )
    if "invalid_grant" in lower or "invalid jwt" in lower:
        return (
            "La clave puede estar desactivada, revocada, mal copiada o el reloj del equipo puede estar muy desajustado."
        )
    if "quota" in lower or "429" in lower:
        return "El proyecto parece tener límite de cuota o uso temporalmente bloqueado."
    if "api has not been used" in lower or "disabled" in lower:
        return "La API necesaria no está habilitada en el proyecto indicado."
    return "No puedo clasificar el error automáticamente. Revisa el detalle técnico justo encima."


@dataclass
class DiagnosticContext:
    credentials_path: Path
    credentials_data: dict[str, Any]
    file_project_id: str
    env_project_id: str
    project_id: str
    client_email: str
    location: str
    model: str


def build_context() -> DiagnosticContext:
    credentials_path = _resolve_path(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"), "credentials.json")
    data, file_project_id, client_email = _safe_project_from_file(credentials_path)
    env_project_id = (os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID") or "").strip()
    project_id = env_project_id or file_project_id
    location = (os.getenv("GOOGLE_CLOUD_LOCATION") or "us-central1").strip()
    model = (os.getenv("VERTEX_MODEL") or "gemini-2.5-flash").strip()

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credentials_path.resolve())
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"

    return DiagnosticContext(
        credentials_path=credentials_path,
        credentials_data=data,
        file_project_id=file_project_id,
        env_project_id=env_project_id,
        project_id=project_id,
        client_email=client_email,
        location=location,
        model=model,
    )


def print_header(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def local_file_check(ctx: DiagnosticContext) -> None:
    print_header("1. Revisión local del fichero")
    print("credentials.json:", ctx.credentials_path)
    print("Proyecto dentro del JSON:", ctx.file_project_id)
    print("Cuenta de servicio:", ctx.client_email)
    print("Proyecto usado por la app:", ctx.project_id)
    print("Región:", ctx.location)
    print("Modelo:", ctx.model)

    if ctx.env_project_id and ctx.env_project_id != ctx.file_project_id:
        raise RuntimeError(
            "El project_id del .env no coincide con el project_id de credentials.json. "
            "Deja ambos iguales o borra GOOGLE_CLOUD_PROJECT y PROJECT_ID del .env para que se lea desde el JSON."
        )
    print("OK: el .env y credentials.json apuntan al mismo proyecto.")


def refresh_service_account_token(ctx: DiagnosticContext):
    print_header("2. Autenticación real de la cuenta de servicio")
    try:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
    except Exception as exc:
        raise RuntimeError(
            "Faltan librerías de autenticación de Google. Ejecuta windows\\00_setup_environment.bat."
        ) from exc

    credentials = service_account.Credentials.from_service_account_file(
        str(ctx.credentials_path),
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    started = time.time()
    credentials.refresh(Request())
    elapsed = round(time.time() - started, 2)
    print(f"OK: Google ha aceptado la clave y ha emitido un token de acceso en {elapsed} s.")
    print("No se imprime el token por seguridad.")
    return credentials


def test_gemini(ctx: DiagnosticContext) -> None:
    print_header("3. Prueba real de Gemini en Vertex AI")
    try:
        from google import genai
        from google.genai import types
    except Exception as exc:
        raise RuntimeError(
            "Falta google-genai en el entorno. Ejecuta windows\\00_setup_environment.bat."
        ) from exc

    client = genai.Client(vertexai=True, project=ctx.project_id, location=ctx.location)
    started = time.time()
    response = client.models.generate_content(
        model=ctx.model,
        contents="Responde únicamente con: OK FridgeChef",
        config=types.GenerateContentConfig(temperature=0.0),
    )
    elapsed = round(time.time() - started, 2)
    text = (response.text or "").strip()
    print(f"OK: Gemini ha respondido en {elapsed} s.")
    print("Respuesta:", text)


def test_firestore(ctx: DiagnosticContext, credentials: Any) -> None:
    print_header("4. Prueba real de Firestore")
    backend = (os.getenv("PERSISTENCE_BACKEND") or "sqlite").strip().lower()
    if not _env_bool("ALLOW_CHAT_PERSISTENCE", False):
        print("INFO: ALLOW_CHAT_PERSISTENCE=false. Salto la prueba de Firestore.")
        return
    if backend != "firestore":
        print("INFO: La app está usando SQLite para la nevera. Firestore queda pendiente para producción futura.")
        return

    try:
        from google.cloud import firestore
    except Exception as exc:
        raise RuntimeError(
            "Falta google-cloud-firestore en el entorno. Ejecuta windows\\00_setup_environment.bat."
        ) from exc

    database = (os.getenv("FIRESTORE_DATABASE") or "(default)").strip()
    collection = (os.getenv("FIRESTORE_COLLECTION") or "fridgechef_sessions").strip()
    document_id = "diagnostic_local_check"

    try:
        client = firestore.Client(project=ctx.project_id, credentials=credentials, database=database)
    except TypeError:
        client = firestore.Client(project=ctx.project_id, credentials=credentials)

    reference = client.collection(collection).document(document_id)
    payload = {
        "event": "diagnostic",
        "source": "FridgeChef local credentials check",
        "ok": True,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    reference.set(payload)
    saved = reference.get()
    if not saved.exists:
        raise RuntimeError("Firestore ha aceptado la escritura, pero no he podido leer el documento de prueba.")
    reference.delete()
    print("OK: Firestore permite escribir, leer y borrar un documento de prueba.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico real de Google Cloud para FridgeChef.")
    parser.add_argument("--skip-firestore", action="store_true", help="No comprobar Firestore.")
    parser.add_argument("--only-gemini", action="store_true", help="Comprobar solo Gemini, además de la autenticación.")
    args = parser.parse_args(argv)

    print("FridgeChef - diagnóstico real de Google Cloud")
    print("No se imprimen claves privadas, tokens ni contraseñas.")

    credentials = None
    try:
        ctx = build_context()
        local_file_check(ctx)
        credentials = refresh_service_account_token(ctx)
        test_gemini(ctx)
        if not args.only_gemini and not args.skip_firestore:
            test_firestore(ctx, credentials)
    except Exception as exc:
        print()
        print("ERROR:", exc)
        print("POSIBLE CAUSA:", _explain_google_error(exc))
        print()
        print("Qué hacer ahora:")
        print("1) Comprueba que el proyecto indicado sigue activo.")
        print("2) Comprueba que esa cuenta de servicio tiene rol Agent Platform User / Vertex AI User.")
        print("3) Comprueba que Gemini/Vertex AI está habilitado en ese proyecto.")
        print("4) Si Firestore falla, comprueba que Firestore está creado y que la cuenta tiene permisos sobre la base de datos.")
        return 1

    print_header("Resultado final")
    print("OK: credentials.json funciona para FridgeChef en este equipo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
