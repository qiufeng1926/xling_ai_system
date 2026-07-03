#!/usr/bin/env bash
# 启动会议 AI（:8001）
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

# shellcheck disable=SC2086
docker run -d \
  --name "$NAME" \
  --restart unless-stopped \
  --network "$NET" \
  -p "${MEETING_API_PORT:-8001}:8001" \
  $UPLOAD_VOL \
  $OUTPUT_VOL \
  $LOGS_VOL \
  -e APP_ENV="${APP_ENV:-production}" \
  -e JWT_SECRET="${JWT_SECRET}" \
  -e PORTAL_API_URL="${INFLUENCER_API_URL}" \
  -e PORTAL_INTERNAL_KEY="${PORTAL_INTERNAL_KEY}" \
  -e CORS_ORIGINS="${CORS_ORIGINS}" \
  -e DB_HOST="${DB_HOST}" \
  -e DB_PORT="${DB_PORT:-3306}" \
  -e DB_USER="${MYSQL_USER}" \
  -e DB_PASSWORD="${MYSQL_PASSWORD}" \
  -e DB_NAME=meeting_ai \
  -e LLM_PROVIDER="${LLM_PROVIDER:-glm}" \
  -e GLM_API_KEY="${GLM_API_KEY:-}" \
  -e GLM_MODEL="${GLM_MODEL:-glm-4-flash}" \
  -e ALIBABA_CLOUD_ACCESS_KEY_ID="${ALIBABA_CLOUD_ACCESS_KEY_ID:-}" \
  -e ALIBABA_CLOUD_ACCESS_KEY_SECRET="${ALIBABA_CLOUD_ACCESS_KEY_SECRET:-}" \
  -e TINGWU_APP_KEY="${TINGWU_APP_KEY:-}" \
  -e TINGWU_REGION="${TINGWU_REGION:-cn-beijing}" \
  -e TINGWU_DOMAIN="${TINGWU_DOMAIN:-tingwu.cn-beijing.aliyuncs.com}" \
  -e MAX_UPLOAD_BYTES="${MAX_UPLOAD_BYTES:-524288000}" \
  "$(img meeting-ai)"

echo "会议 AI 已启动: $NAME -> http://${MEETING_API_HOST:-127.0.0.1}:${MEETING_API_PORT:-8001}"
