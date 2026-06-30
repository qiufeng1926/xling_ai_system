#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

NET="$(ensure_network)"
NAME="${REDIS_CONTAINER_NAME:-xlink_redis}"
stop_rm_if_exists "$NAME"

docker run -d \
  --name "$NAME" \
  --restart unless-stopped \
  --network "$NET" \
  -p "${REDIS_PORT:-6379}:6379" \
  redis:7-alpine

echo "Redis 已启动: $NAME (端口 ${REDIS_PORT:-6379})"
