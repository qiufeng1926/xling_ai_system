#!/usr/bin/env bash
# 启动会议 AI（:8001）— meeting_ai/.env + distributed.env
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

NET="$(ensure_network)"
NAME="${MEETING_CONTAINER_NAME:-xlink_meeting_ai}"
stop_rm_if_exists "$NAME"

UPLOAD_VOL="$(volume_mount meeting_upload /app/upload)"
OUTPUT_VOL="$(volume_mount meeting_output /app/output)"
LOGS_VOL="$(logs_volume_mount meeting_ai /app/logs)"
SERVICE_ENV="$(service_env_path "meeting_ai/.env")"

APP_ENV="${APP_ENV:-development}"
JWT_SECRET="${JWT_SECRET:-dev-local-secret-key-at-least-32-characters-long}"
INTERNAL_KEY="${PORTAL_INTERNAL_KEY:-dev-flybook-internal-key-change-me}"

mapfile -d '' CORS_ARGS < <(optional_env_args CORS_ORIGINS)

# shellcheck disable=SC2086
docker run -d \
  --name "$NAME" \
  --restart unless-stopped \
  --network "$NET" \
  -p "${MEETING_API_PORT:-8001}:8001" \
  $UPLOAD_VOL \
  $OUTPUT_VOL \
  $LOGS_VOL \
  --env-file "$SERVICE_ENV" \
  "${CORS_ARGS[@]}" \
  -e APP_ENV="$APP_ENV" \
  -e JWT_SECRET="$JWT_SECRET" \
  -e PORTAL_API_URL="${INFLUENCER_API_URL:-http://xlink_influencer_backend:8000}" \
  -e PORTAL_INTERNAL_KEY="$INTERNAL_KEY" \
  -e DB_HOST="${DB_HOST:-xlink_mysql}" \
  -e DB_PORT="${DB_PORT:-3306}" \
  -e DB_USER="${MYSQL_USER:-app_user}" \
  -e DB_PASSWORD="${MYSQL_PASSWORD:-app123}" \
  -e DB_NAME=meeting_ai \
  -e FFMPEG_PATH=/usr/bin \
  "$(img meeting-ai)"

echo "会议 AI 已启动: $NAME -> http://${MEETING_API_HOST:-127.0.0.1}:${MEETING_API_PORT:-8001}"
