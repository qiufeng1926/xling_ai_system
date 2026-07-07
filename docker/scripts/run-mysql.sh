#!/usr/bin/env bash
# 启动 MySQL（基础设施节点）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

NET="$(ensure_network)"
NAME="${MYSQL_CONTAINER_NAME:-xlink_mysql}"
stop_rm_if_exists "$NAME"

MYSQL_VOL="$(volume_mount mysql_data /var/lib/mysql)"
# shellcheck disable=SC2086
docker run -d \
  --name "$NAME" \
  --restart unless-stopped \
  --network "$NET" \
  -p "${MYSQL_PORT:-3306}:3306" \
  $MYSQL_VOL \
  -v "$ROOT_DIR/Information_Aggregation/scripts/init.sql:/docker-entrypoint-initdb.d/01-influencer.sql:ro" \
  -v "$ROOT_DIR/docker/mysql/02-meeting-ai.sql:/docker-entrypoint-initdb.d/02-meeting-ai.sql:ro" \
  -v "$ROOT_DIR/docker/mysql/03-grants.sql:/docker-entrypoint-initdb.d/03-grants.sql:ro" \
  -e MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD}" \
  -e MYSQL_DATABASE=influencer_db \
  -e MYSQL_USER="${MYSQL_USER}" \
  -e MYSQL_PASSWORD="${MYSQL_PASSWORD}" \
  mysql:8.0 \
  --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_unicode_ci

echo "MySQL 已启动: $NAME (端口 ${MYSQL_PORT:-3306})"
