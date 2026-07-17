#!/bin/sh
set -eu

BASE_DIR="${FRIDGECHEF_BASE_DIR:-/volume1/docker/fridgechef}"
REPO_URL="${FRIDGECHEF_REPO_URL:-https://github.com/Pedrormm/fridgechef-ai-assistant.git}"
BRANCH="${FRIDGECHEF_BRANCH:-main}"
CONTAINER_NAME="${FRIDGECHEF_CONTAINER_NAME:-fridgechef-ai}"
IMAGE_PREFIX="${FRIDGECHEF_IMAGE_PREFIX:-fridgechef-ai}"
HOST_PORT="${FRIDGECHEF_HOST_PORT:-8501}"
CONTAINER_PORT="${FRIDGECHEF_CONTAINER_PORT:-8080}"

REPO_DIR="$BASE_DIR/repo"
BUILD_DIR="$BASE_DIR/build-src"
DATA_DIR="$BASE_DIR/data"
PHOTOS_DIR="$BASE_DIR/photos"
BACKUPS_DIR="$BASE_DIR/backups"
LOGS_DIR="$BASE_DIR/logs"
SECRETS_DIR="$BASE_DIR/secrets"
CONFIG_DIR="$BASE_DIR/config"
ENV_FILE="$CONFIG_DIR/.env.production"
STAMP="$(date +%Y%m%d_%H%M%S)"

log() {
  printf '\n==> %s\n' "$*"
}

fail() {
  printf '\nERROR: %s\n' "$*" >&2
  exit 1
}

run_git() {
  docker run --rm \
    -v "$REPO_DIR:/repo" \
    -w /repo \
    alpine/git:latest "$@"
}

prepare_directories() {
  mkdir -p \
    "$BASE_DIR" "$DATA_DIR" "$PHOTOS_DIR" "$BACKUPS_DIR" \
    "$LOGS_DIR" "$SECRETS_DIR" "$CONFIG_DIR"

  [ -f "$ENV_FILE" ] || fail "Falta $ENV_FILE. No se ha modificado ni eliminado tu configuración."
  [ -f "$SECRETS_DIR/credentials.json" ] || fail "Falta $SECRETS_DIR/credentials.json."

  chmod 700 "$SECRETS_DIR" 2>/dev/null || true
  chmod 600 "$ENV_FILE" "$SECRETS_DIR/credentials.json" 2>/dev/null || true
}

backup_sqlite() {
  if [ -f "$DATA_DIR/fridgechef.db" ]; then
    cp -p "$DATA_DIR/fridgechef.db" "$BACKUPS_DIR/fridgechef_before_recovery_${STAMP}.db"
    log "SQLite guardado en $BACKUPS_DIR/fridgechef_before_recovery_${STAMP}.db"
  else
    log "No existe todavía $DATA_DIR/fridgechef.db; no hay SQLite que copiar"
  fi
}

sync_repository() {
  log "Sincronizando un clon limpio con origin/$BRANCH"

  if [ ! -d "$REPO_DIR/.git" ]; then
    rm -rf "$REPO_DIR" "$REPO_DIR.tmp"
    docker run --rm \
      -v "$BASE_DIR:/workspace" \
      alpine/git:latest \
      clone --branch "$BRANCH" "$REPO_URL" /workspace/repo.tmp
    mv "$REPO_DIR.tmp" "$REPO_DIR"
  fi

  run_git remote set-url origin "$REPO_URL"
  run_git fetch --prune origin "$BRANCH"
  run_git checkout -B "$BRANCH" "origin/$BRANCH"
  run_git reset --hard "origin/$BRANCH"
  run_git clean -fdx

  [ -f "$REPO_DIR/src/fridgechef/action_results.py" ] || \
    fail "El clon de GitHub no contiene src/fridgechef/action_results.py. Se detiene antes de tocar el contenedor."
  [ -f "$REPO_DIR/streamlit_app/app.py" ] || \
    fail "El clon de GitHub no contiene streamlit_app/app.py."
  [ -f "$REPO_DIR/Dockerfile.git.nas" ] || \
    fail "El clon de GitHub no contiene Dockerfile.git.nas."
  [ -d "$REPO_DIR/tests" ] || \
    fail "El clon de GitHub no contiene la carpeta tests."
}

prepare_build_context() {
  log "Creando un contexto de compilación limpio sin modificar el clon Git"
  rm -rf "$BUILD_DIR"
  mkdir -p "$BUILD_DIR"
  docker run --rm \
    -v "$REPO_DIR:/source:ro" \
    -v "$BUILD_DIR:/build" \
    alpine:3.20 \
    sh -c 'cd /source && tar --exclude=.git -cf - . | tar -xf - -C /build'

  [ -f "$BUILD_DIR/src/fridgechef/action_results.py" ] || \
    fail "El contexto de compilación ha perdido action_results.py."
}

apply_production_compatibility() {
  log "Aplicando compatibilidad determinista de Streamlit al contexto de producción"

  docker run --rm -i \
    -v "$BUILD_DIR:/build" \
    python:3.11-slim \
    python - /build/streamlit_app/app.py <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
source = path.read_text(encoding="utf-8")
original = source

# Streamlit selectbox does not accept filter_mode in the pinned production API.
source = re.sub(r"(?m)^\s*filter_mode=None,\s*\n", "", source)

old = "        with st.expander(title, expanded=initially_expanded):\n"
new = (
    "        with st.expander(\n"
    "            title,\n"
    "            expanded=initially_expanded,\n"
    "            key=f\"{key_scope}_expander\",\n"
    "            width=\"stretch\",\n"
    "        ):\n"
)
if old in source:
    source = source.replace(old, new, 1)
elif new not in source:
    raise SystemExit("No se ha encontrado la estructura esperada del desplegable de Alimentos guardados.")

if "from src.fridgechef.action_results import" not in source:
    raise SystemExit("app.py no contiene el contrato esperado con action_results.")
if "collapsible=True" not in source or "initially_expanded=False" not in source:
    raise SystemExit("No está presente el desplegable plegado de Alimentos guardados.")
if "filter_mode=" in source:
    raise SystemExit("Sigue existiendo un argumento filter_mode incompatible.")

if source != original:
    path.write_text(source, encoding="utf-8")
    print("Compatibilidad aplicada a streamlit_app/app.py")
else:
    print("La compatibilidad ya estaba aplicada")
PY
}

build_and_validate_candidate() {
  COMMIT_FULL="$(run_git rev-parse HEAD)"
  COMMIT_SHORT="$(run_git rev-parse --short=12 HEAD)"
  IMAGE_TAG="${IMAGE_PREFIX}:git-${COMMIT_SHORT}"
  export COMMIT_FULL COMMIT_SHORT IMAGE_TAG

  log "Construyendo candidato $IMAGE_TAG desde main $COMMIT_SHORT"
  docker build \
    --pull \
    --no-cache \
    --label "org.opencontainers.image.source=$REPO_URL" \
    --label "org.opencontainers.image.revision=$COMMIT_FULL" \
    -f "$BUILD_DIR/Dockerfile.git.nas" \
    -t "$IMAGE_TAG" \
    "$BUILD_DIR"

  log "Comprobando que el módulo ausente está realmente dentro de la imagen"
  docker run --rm -i "$IMAGE_TAG" python - <<'PY'
from pathlib import Path
from src.fridgechef.action_results import restore_manual_parse_result, snapshot_manual_parse_result

required = Path("/app/src/fridgechef/action_results.py")
assert required.is_file(), f"Falta {required}"
assert callable(restore_manual_parse_result)
assert callable(snapshot_manual_parse_result)
print("OK: action_results está instalado e importable")
PY

  log "Compilando todo el código Python del candidato"
  docker run --rm "$IMAGE_TAG" \
    python -m compileall -q src streamlit_app tests scripts

  log "Ejecutando la suite completa de pruebas del repositorio"
  docker run --rm "$IMAGE_TAG" python -m pytest -q

  log "Ejecutando una sesión real de Streamlit antes de sustituir producción"
  docker run --rm -i \
    --env-file "$ENV_FILE" \
    -e ALLOW_CHAT_PERSISTENCE=false \
    -e BLINK_ENABLED=false \
    -e RECIPE_IMAGES_ENABLED=false \
    -e LOCAL_DATABASE_PATH=/tmp/fridgechef_preflight.db \
    -v "$SECRETS_DIR/credentials.json:/run/secrets/credentials.json:ro" \
    "$IMAGE_TAG" python - <<'PY'
from streamlit.testing.v1 import AppTest

app = AppTest.from_file("/app/streamlit_app/app.py", default_timeout=120)
app.run()
exceptions = list(app.exception)
if exceptions:
    for exception in exceptions:
        print(exception)
    raise SystemExit("La aplicación produjo una excepción en la prueba Streamlit.")
print("OK: Streamlit renderizó la aplicación sin excepciones")
PY
}

start_candidate() {
  log "Sustituyendo el contenedor únicamente después de superar todas las pruebas"

  docker logs --tail 500 "$CONTAINER_NAME" \
    > "$LOGS_DIR/before_recovery_${STAMP}.log" 2>&1 || true
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

  docker run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    --env-file "$ENV_FILE" \
    -p "$HOST_PORT:$CONTAINER_PORT" \
    -v "$DATA_DIR:/app/data" \
    -v "$PHOTOS_DIR:/app/photos" \
    -v "$BACKUPS_DIR:/app/backups" \
    -v "$LOGS_DIR:/app/logs" \
    -v "$SECRETS_DIR:/app/secrets" \
    -v "$SECRETS_DIR/credentials.json:/run/secrets/credentials.json:ro" \
    "$IMAGE_TAG" >/dev/null
}

wait_and_verify() {
  log "Esperando a que el nuevo contenedor esté operativo"
  attempt=1
  while [ "$attempt" -le 60 ]; do
    docker_status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$CONTAINER_NAME" 2>/dev/null || true)"
    if [ "$docker_status" = "unhealthy" ] || [ "$docker_status" = "exited" ] || [ "$docker_status" = "dead" ]; then
      docker logs --tail 400 "$CONTAINER_NAME" >&2 || true
      fail "El candidato terminó en estado $docker_status."
    fi
    if curl -fsS "http://127.0.0.1:${HOST_PORT}/_stcore/health" >/dev/null 2>&1; then
      break
    fi
    sleep 3
    attempt=$((attempt + 1))
  done

  curl -fsS "http://127.0.0.1:${HOST_PORT}/_stcore/health" >/dev/null 2>&1 || {
    docker logs --tail 400 "$CONTAINER_NAME" >&2 || true
    fail "Streamlit no respondió correctamente en el puerto $HOST_PORT."
  }

  docker exec -i "$CONTAINER_NAME" python - <<'PY'
from pathlib import Path
from src.fridgechef.action_results import restore_manual_parse_result
assert Path("/app/src/fridgechef/action_results.py").is_file()
assert callable(restore_manual_parse_result)
print("OK: contrato de imports verificado dentro del contenedor activo")
PY

  sleep 5
  critical="$({ docker logs --since 10m "$CONTAINER_NAME" 2>&1 || true; } | grep -iE 'Uncaught app execution|ModuleNotFoundError|ImportError|Traceback|StreamlitAPIException|DuplicateElementKey|TypeError:.*unexpected keyword' || true)"
  if [ -n "$critical" ]; then
    printf '%s\n' "$critical" >&2
    fail "Los logs del nuevo contenedor contienen un error crítico."
  fi

  WORKTREE_STATUS="$(run_git status --porcelain)"
  [ -z "$WORKTREE_STATUS" ] || fail "El clon Git no está limpio después del despliegue."
  RUNNING_IMAGE="$(docker inspect --format '{{.Config.Image}}' "$CONTAINER_NAME")"
  RUNNING_REVISION="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$RUNNING_IMAGE")"
  REMOTE_URL="$(run_git remote get-url origin)"
  LOCAL_HEAD="$(run_git rev-parse HEAD)"
  REMOTE_HEAD="$(run_git rev-parse "origin/$BRANCH")"

  [ "$LOCAL_HEAD" = "$REMOTE_HEAD" ] || fail "El clon local no coincide con origin/$BRANCH."
  [ "$RUNNING_REVISION" = "$LOCAL_HEAD" ] || fail "La imagen activa no corresponde al commit descargado."

  log "RECUPERACIÓN COMPLETADA"
  printf 'Repositorio: %s\n' "$REMOTE_URL"
  printf 'Rama: %s\n' "$BRANCH"
  printf 'Commit main: %s\n' "$LOCAL_HEAD"
  printf 'Imagen activa: %s\n' "$RUNNING_IMAGE"
  printf 'Contenedor: %s\n' "$CONTAINER_NAME"
  printf 'Health: ok\n'
  printf 'URL local: http://127.0.0.1:%s\n' "$HOST_PORT"
  printf 'URL Tailscale: https://prnas.tail942ed2.ts.net/\n'
}

prepare_directories
backup_sqlite
sync_repository
prepare_build_context
apply_production_compatibility
build_and_validate_candidate
start_candidate
wait_and_verify
