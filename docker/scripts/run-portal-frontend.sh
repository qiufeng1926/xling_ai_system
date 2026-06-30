#!/usr/bin/env bash
# 启动门户前端 Nginx（:80）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

NET="$(ensure_network)"
NAME="${PORTAL_CONTAINER_NAME:-xlink_portal_frontend}"
stop_rm_if_exists "$NAME"

# Nginx 模板使用 host:port（非 docker 服务名时填 distributed.env 中的地址）
INFLUENCER_UPSTREAM="${INFLUENCER_API_HOST:-influencer-backend}:${INFLUENCER_API_PORT:-8000}"
MEETING_UPSTREAM="${MEETING_API_HOST:-meeting-ai}:${MEETING_API_PORT:-8001}"
FLYBOOK_UPSTREAM="${FLYBOOK_API_HOST:-flybook}:${FLYBOOK_API_PORT:-8002}"

docker run -d \
  --name "$NAME" \
  --restart unless-stopped \
  --network "$NET" \
  -p "${PORTAL_HTTP_PORT:-80}:80" \
  -e INFLUENCER_API_HOST="$INFLUENCER_UPSTREAM" \
  -e MEETING_API_HOST="$MEETING_UPSTREAM" \
  -e FLYBOOK_API_HOST="$FLYBOOK_UPSTREAM" \
  "$(img portal-frontend)"

echo "门户前端已启动: $NAME -> http://127.0.0.1:${PORTAL_HTTP_PORT:-80}"
