from __future__ import annotations

import json
from pathlib import Path

ROOT = Path.cwd()
credentials = ROOT / "credentials.json"
project_id = ""

if credentials.exists():
    try:
        project_id = json.loads(credentials.read_text(encoding="utf-8")).get("project_id", "")
    except Exception:
        project_id = ""

env = f"""# FridgeChef AI - generated local environment
APP_NAME=FridgeChef_AI_PedroRamonMoreno
APP_ENV=dev
GOOGLE_APPLICATION_CREDENTIALS=credentials.json
GOOGLE_CLOUD_PROJECT={project_id}
PROJECT_ID={project_id}
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_GENAI_USE_ENTERPRISE=TRUE
VERTEX_MODEL=gemini-2.5-flash
ALLOW_CHAT_PERSISTENCE=false
ALLOW_IMAGE_STORAGE=false
BUCKET_NAME=
FIRESTORE_DATABASE=(default)
FIRESTORE_COLLECTION=fridgechef_sessions
ENCRYPTION_ENABLED=true
FRIDGECHEF_MASTER_KEY=
APP_ENCRYPTION_KEY=
MAX_IMAGE_MB=10
MCP_ENABLED=false
MCP_SERVER_URL=http://localhost:8088/mcp
MCP_AUTH_TOKEN=local-dev-token-change-me
BLINK_ENABLED=false
BLINK_AUTH_FILE=blink_auth.json
BLINK_OUTPUT_FILE=photos/blink_latest.jpg
BLINK_MAX_PHOTO_AGE_SECONDS=120
BLINK_MAX_STALE_SECONDS=120
AUTOMATION_ENABLED=false
AUTOMATION_ENGINE=python
AUTOMATION_SEND_EMAIL=false
AUTOMATION_EMAIL_TO=
EMAIL_ENABLED=false
EMAIL_TO=
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
"""

(ROOT / ".env").write_text(env, encoding="utf-8")
print(".env generated at", ROOT / ".env")
if project_id:
    print("PROJECT_ID loaded from credentials.json:", project_id)
else:
    print("PROJECT_ID was not found. Fill GOOGLE_CLOUD_PROJECT manually or check credentials.json.")
