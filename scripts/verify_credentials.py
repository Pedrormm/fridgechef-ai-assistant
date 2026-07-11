from __future__ import annotations

import json
import os
import re
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

PROJECT_ROOT = Path.cwd()
ENV_FILE = PROJECT_ROOT / ".env"

if load_dotenv and ENV_FILE.exists():
    load_dotenv(ENV_FILE)


def fail(message: str) -> None:
    """Print a clear error and stop the verification script."""
    print(f"ERROR: {message}")
    raise SystemExit(1)


def ok(message: str) -> None:
    """Print a successful verification line."""
    print(f"OK: {message}")


def resolve_path(value: str, default: str) -> Path:
    """Resolve a path from .env relative to the project root when needed."""
    raw = (value or default).strip()
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


credentials_path = resolve_path(os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""), "credentials.json")
internal_camera_auth_path = resolve_path(os.getenv("BLINK_AUTH_FILE", ""), "blink_auth.json")

if not ENV_FILE.exists():
    fail(".env was not found. Copy .env.example to .env and adjust local values if needed.")
ok(".env found")

if not credentials_path.exists():
    fail(f"credentials.json was not found at: {credentials_path}")

try:
    data = json.loads(credentials_path.read_text(encoding="utf-8"))
except Exception as exc:
    fail(f"credentials.json is not valid JSON: {exc}")

required = {"type", "project_id", "client_email", "private_key"}
missing = required - set(data)
if missing:
    fail(f"credentials.json does not look like a service account. Missing fields: {sorted(missing)}")
if data.get("type") != "service_account":
    fail("credentials.json must be a service account file.")

project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID") or data.get("project_id")
if not project_id:
    fail("project_id could not be found in .env or credentials.json.")

ok(f"credentials.json is valid. Project detected: {project_id}")
ok(f"Service account detected: {data.get('client_email')}")

if not internal_camera_auth_path.exists():
    print("INFO: Internal camera auth file was not found. The web app will still work with manual input and uploaded photos.")
else:
    try:
        internal_camera_auth = json.loads(internal_camera_auth_path.read_text(encoding="utf-8"))
        if any(key in internal_camera_auth for key in ["token", "refresh_token", "username"]):
            ok("Internal camera auth file found with a compatible structure.")
        else:
            print("INFO: Internal camera auth file exists, but it does not look like a complete auth file yet.")
    except Exception as exc:
        print(f"INFO: Internal camera auth file exists, but it is not valid JSON: {exc}")

email = os.getenv("AUTOMATION_EMAIL_TO") or os.getenv("EMAIL_TO", "")
if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
    print("INFO: The configured email address does not look valid. Email sending will be skipped.")

print("Verification completed. No private keys, passwords or tokens were printed.")
