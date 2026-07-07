#!/usr/bin/env bash
# 启动达人/门户 API（:8000）— backend/.env + distributed.env
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

NET="$(ensure_network)"
NAME="${INFLUENCER_CONTAINER_NAME:-xlink_influencer_backend}"
stop_rm_if_exists "$NAME"

LOGS_VOL="$(logs_volume_mount influencer_backend /app/logs)"
COOKIES_VOL="$(volume_mount influencer_cookies /app/cookies)"
SERVICE_ENV="$(service_env_path "Information_Aggregation/backend/.env")"

JWT_SECRET="${JWT_SECRET:-dev-local-secret-key-at-least-32-characters-long}"
INTERNAL_KEY="${PORTAL_INTERNAL_KEY:-dev-flybook-internal-key-change-me}"
DEBUG_FLAG="${DEBUG:-false}"

mapfile -d '' CORS_ARGS < <(optional_env_args CORS_ORIGINS)

# shellcheck disable=SC2086
docker run -d \
  --name "$NAME" \
  --restart unless-stopped \
  --network "$NET" \
  -p "${INFLUENCER_API_PORT:-8000}:8000" \
  $LOGS_VOL \
  $COOKIES_VOL \
  --env-file "$SERVICE_ENV" \
  "${CORS_ARGS[@]}" \
  -e DB_HOST="${DB_HOST:-xlink_mysql}" \
  -e DB_PORT="${DB_PORT:-3306}" \
  -e DB_USER="${MYSQL_USER:-app_user}" \
  -e DB_PASSWORD="${MYSQL_PASSWORD:-app123}" \
  -e DB_NAME=influencer_db \
  -e REDIS_URL="${REDIS_URL:-redis://xlink_redis:6379/0}" \
  -e SECRET_KEY="$JWT_SECRET" \
  -e DEBUG="$DEBUG_FLAG" \
  -e API_HOST=0.0.0.0 \
  -e API_PORT=8000 \
  -e FLYBOOK_API_URL="${FLYBOOK_API_URL:-http://xlink_flybook:8002}" \
  -e MEETING_AI_API_URL="${MEETING_AI_API_URL:-http://xlink_meeting_ai:8001}" \
  -e PORTAL_INTERNAL_KEY="$INTERNAL_KEY" \
  -e FLYBOOK_INTERNAL_KEY="$INTERNAL_KEY" \
  -e PLAYWRIGHT_HEADLESS=true \
  "$(img influencer-backend)"

echo "达人后端已启动: $NAME -> http://${INFLUENCER_API_HOST:-127.0.0.1}:${INFLUENCER_API_PORT:-8000}"
