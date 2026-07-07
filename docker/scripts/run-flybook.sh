#!/usr/bin/env bash
# 启动飞书后端（:8002）— flybook/.env + distributed.env
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

NET="$(ensure_network)"
NAME="${FLYBOOK_CONTAINER_NAME:-xlink_flybook}"
stop_rm_if_exists "$NAME"

LOGS_VOL="$(logs_volume_mount flybook /app/logs)"
SERVICE_ENV="$(service_env_path "flybook/.env")"

APP_ENV="${APP_ENV:-development}"
JWT_SECRET="${JWT_SECRET:-dev-local-secret-key-at-least-32-characters-long}"
INTERNAL_KEY="${PORTAL_INTERNAL_KEY:-dev-flybook-internal-key-change-me}"

mapfile -d '' CORS_ARGS < <(optional_env_args CORS_ORIGINS)
mapfile -d '' PORTAL_FRONT_ARGS < <(optional_env_args PORTAL_FRONTEND_URL)

# shellcheck disable=SC2086
docker run -d \
  --name "$NAME" \
  --restart unless-stopped \
  --network "$NET" \
  -p "${FLYBOOK_API_PORT:-8002}:8002" \
  $LOGS_VOL \
  --env-file "$SERVICE_ENV" \
  "${CORS_ARGS[@]}" \
  "${PORTAL_FRONT_ARGS[@]}" \
  -e APP_ENV="$APP_ENV" \
  -e JWT_SECRET="$JWT_SECRET" \
  -e PORTAL_API_URL="${INFLUENCER_API_URL:-http://xlink_influencer_backend:8000}" \
  -e FLYBOOK_INTERNAL_KEY="$INTERNAL_KEY" \
  "$(img flybook)"

echo "飞书后端已启动: $NAME -> http://${FLYBOOK_API_HOST:-127.0.0.1}:${FLYBOOK_API_PORT:-8002}"
