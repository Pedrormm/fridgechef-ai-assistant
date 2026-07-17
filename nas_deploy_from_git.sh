#!/bin/sh
set -eu

BASE_DIR="${FRIDGECHEF_BASE_DIR:-/volume1/docker/fridgechef}"
REPO_URL="${FRIDGECHEF_REPO_URL:-https://github.com/Pedrormm/fridgechef-ai-assistant.git}"
BRANCH="${FRIDGECHEF_BRANCH:-main}"
CONTAINER_NAME="${FRIDGECHEF_CONTAINER_NAME:-fridgechef-ai}"
IMAGE_PREFIX="${FRIDGECHEF_IMAGE_PREFIX:-fridgechef-ai}"
HOST_PORT="${FRIDGECHEF_HOST_PORT:-8501}"
CONTAINER_PORT="${FRIDGECHEF_CONTAINER_PORT:-8080}"
RUN_TESTS="${FRIDGECHEF_RUN_TESTS:-1}"

REPO_DIR="$BASE_DIR/repo"
DATA_DIR="$BASE_DIR/data"
PHOTOS_DIR="$BASE_DIR/photos"
BACKUPS_DIR="$BASE_DIR/backups"
LOGS_DIR="$BASE_DIR/logs"
SECRETS_DIR="$BASE_DIR/secrets"
CONFIG_DIR="$BASE_DIR/config"
ENV_FILE="$CONFIG_DIR/.env.production"

log() {
  printf '\n==> %s\n' "$*"
}

fail() {
  printf '\nERROR: %s\n' "$*" >&2
  exit 1
}

run_git() {
  if command -v git >/dev/null 2>&1; then
    git "$@"
  else
    docker run --rm -v "$REPO_DIR:/repo" -w /repo alpine/git:latest "$@"
  fi
}

clone_repo() {
  mkdir -p "$BASE_DIR"
  if [ -d "$REPO_DIR/.git" ]; then
    log "Updating existing Git clone"
    run_git fetch --prune origin "$BRANCH"
    run_git reset --hard "origin/$BRANCH"
    run_git clean -fdx
    return
  fi

  log "Creating a clean Git clone"
  rm -rf "$REPO_DIR" "$REPO_DIR.tmp"
  if command -v git >/dev/null 2>&1; then
    git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$REPO_DIR.tmp"
  else
    docker run --rm -v "$BASE_DIR:/workspace" alpine/git:latest \
      clone --branch "$BRANCH" --depth 1 "$REPO_URL" /workspace/repo.tmp
  fi
  mv "$REPO_DIR.tmp" "$REPO_DIR"
}

ensure_env_value() {
  key="$1"
  value="$2"
  tmp_file="$ENV_FILE.tmp"

  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed "s|^${key}=.*|${key}=${value}|" "$ENV_FILE" > "$tmp_file"
    mv "$tmp_file" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

validate_layout() {
  [ -f "$ENV_FILE" ] || fail "Missing $ENV_FILE. Keep your existing production env file there."
  [ -f "$SECRETS_DIR/credentials.json" ] || fail "Missing $SECRETS_DIR/credentials.json."

  mkdir -p "$DATA_DIR" "$PHOTOS_DIR" "$BACKUPS_DIR" "$LOGS_DIR" "$SECRETS_DIR" "$CONFIG_DIR"

  # Keep production deterministic. SQLite and NAS bind mounts are the source of truth.
  ensure_env_value "APP_ENV" "prod"
  ensure_env_value "PERSISTENCE_BACKEND" "sqlite"
  ensure_env_value "LOCAL_DATABASE_PATH" "/app/data/fridgechef.db"
  ensure_env_value "GOOGLE_APPLICATION_CREDENTIALS" "/run/secrets/credentials.json"
  ensure_env_value "MCP_ENABLED" "false"

  chmod 700 "$SECRETS_DIR" || true
  chmod 600 "$ENV_FILE" "$SECRETS_DIR/credentials.json" 2>/dev/null || true
}

run_validation() {
  image_tag="$1"
  if [ "$RUN_TESTS" != "1" ]; then
    log "Skipping tests because FRIDGECHEF_RUN_TESTS=$RUN_TESTS"
    return
  fi

  log "Running tests inside the production image"
  docker run --rm "$image_tag" python -m pytest -q

  log "Compiling Python sources inside the production image"
  docker run --rm "$image_tag" python -m compileall -q src streamlit_app tests scripts
}

start_container() {
  image_tag="$1"
  stamp="$(date +%Y%m%d_%H%M%S)"

  if [ -f "$DATA_DIR/fridgechef.db" ]; then
    log "Backing up SQLite before replacing the container"
    cp "$DATA_DIR/fridgechef.db" "$BACKUPS_DIR/fridgechef_predeploy_${stamp}.db"
  fi

  log "Replacing the running container"
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
    "$image_tag" >/dev/null
}

wait_for_health() {
  log "Waiting for Streamlit health check"
  attempt=1
  while [ "$attempt" -le 40 ]; do
    if curl -fsS "http://127.0.0.1:${HOST_PORT}/_stcore/health" >/dev/null 2>&1; then
      printf 'ok\n'
      return
    fi
    sleep 3
    attempt=$((attempt + 1))
  done

  docker logs --tail 300 "$CONTAINER_NAME" >&2 || true
  fail "The container did not become healthy. See the logs above."
}

log "Preparing folders and production configuration"
mkdir -p "$DATA_DIR" "$PHOTOS_DIR" "$BACKUPS_DIR" "$LOGS_DIR" "$SECRETS_DIR" "$CONFIG_DIR"
validate_layout

clone_repo
COMMIT="$(run_git rev-parse --short HEAD)"
IMAGE_TAG="${IMAGE_PREFIX}:git-${COMMIT}"

log "Building $IMAGE_TAG from GitHub commit $COMMIT"
docker build -f "$REPO_DIR/Dockerfile.git.nas" -t "$IMAGE_TAG" "$REPO_DIR"

run_validation "$IMAGE_TAG"
start_container "$IMAGE_TAG"
wait_for_health

log "Deployment completed"
printf 'Commit: %s\n' "$COMMIT"
printf 'Image: %s\n' "$IMAGE_TAG"
printf 'Container: %s\n' "$CONTAINER_NAME"
printf 'Private URL: http://127.0.0.1:%s\n' "$HOST_PORT"
printf 'Tailscale/Funnel URL: use your existing https://prnas.tail942ed2.ts.net/ endpoint.\n'

docker ps --filter "name=${CONTAINER_NAME}"
