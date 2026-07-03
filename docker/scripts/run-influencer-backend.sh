#!/usr/bin/env bash
# 启动达人/门户 API（:8000）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

NET="$(ensure_network)"
NAME="${INFLUENCER_CONTAINER_NAME:-xlink_influencer_backend}"
stop_rm_if_exists "$NAME"

LOGS_VOL="$(logs_volume_mount influencer_backend /app/logs)"
COOKIES_VOL="$(volume_mount influencer_cookies /app/cookies)"

# shellcheck disable=SC2086
docker run -d \
  --name "$NAME" \
  --restart unless-stopped \
  --network "$NET" \
  -p "${INFLUENCER_API_PORT:-8000}:8000" \
  $LOGS_VOL \
  $COOKIES_VOL \
  -e DB_HOST="${DB_HOST}" \
  -e DB_PORT="${DB_PORT:-3306}" \
  -e DB_USER="${MYSQL_USER}" \
  -e DB_PASSWORD="${MYSQL_PASSWORD}" \
  -e DB_NAME=influencer_db \
  -e REDIS_URL="${REDIS_URL}" \
  -e SECRET_KEY="${JWT_SECRET}" \
  -e DEBUG="${DEBUG:-false}" \
  -e API_HOST=0.0.0.0 \
  -e API_PORT=8000 \
  -e CORS_ORIGINS="${CORS_ORIGINS}" \
  -e FLYBOOK_API_URL="${FLYBOOK_API_URL}" \
  -e MEETING_AI_API_URL="${MEETING_AI_API_URL}" \
  -e PORTAL_INTERNAL_KEY="${PORTAL_INTERNAL_KEY}" \
  -e FLYBOOK_INTERNAL_KEY="${PORTAL_INTERNAL_KEY}" \
  -e ADMIN_USERNAME="${ADMIN_USERNAME:-admin}" \
  -e ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin123}" \
  "$(img influencer-backend)"

echo "达人后端已启动: $NAME -> http://${INFLUENCER_API_HOST:-127.0.0.1}:${INFLUENCER_API_PORT:-8000}"
