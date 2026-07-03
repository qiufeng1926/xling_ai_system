#!/usr/bin/env bash
# 启动飞书后端（:8002）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

NET="$(ensure_network)"
NAME="${FLYBOOK_CONTAINER_NAME:-xlink_flybook}"
stop_rm_if_exists "$NAME"

LOGS_VOL="$(logs_volume_mount flybook /app/logs)"

# shellcheck disable=SC2086
docker run -d \
  --name "$NAME" \
  --restart unless-stopped \
  --network "$NET" \
  -p "${FLYBOOK_API_PORT:-8002}:8002" \
  $LOGS_VOL \
  -e APP_ENV="${APP_ENV:-production}" \
  -e JWT_SECRET="${JWT_SECRET}" \
  -e PORTAL_API_URL="${INFLUENCER_API_URL}" \
  -e PORTAL_FRONTEND_URL="${PORTAL_FRONTEND_URL}" \
  -e FLYBOOK_INTERNAL_KEY="${PORTAL_INTERNAL_KEY}" \
  -e CORS_ORIGINS="${CORS_ORIGINS}" \
  -e FEISHU_APP_ID="${FEISHU_APP_ID:-}" \
  -e FEISHU_APP_SECRET="${FEISHU_APP_SECRET:-}" \
  -e FEISHU_OAUTH_REDIRECT_URI="${FEISHU_OAUTH_REDIRECT_URI}" \
  -e FEISHU_VERIFICATION_TOKEN="${FEISHU_VERIFICATION_TOKEN:-}" \
  -e FEISHU_ENCRYPT_KEY="${FEISHU_ENCRYPT_KEY:-}" \
  -e FEISHU_MESSENGER_URL="${FEISHU_MESSENGER_URL:-}" \
  "$(img flybook)"

echo "飞书后端已启动: $NAME -> http://${FLYBOOK_API_HOST:-127.0.0.1}:${FLYBOOK_API_PORT:-8002}"
