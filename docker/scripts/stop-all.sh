#!/usr/bin/env bash
# 停止并删除 xlink 相关容器（不删数据卷）
set -euo pipefail

NAMES=(
  xlink_portal_frontend
  xlink_flybook
  xlink_meeting_ai
  xlink_influencer_backend
  xlink_redis
  xlink_mysql
)

for n in "${NAMES[@]}"; do
  if docker ps -a --format '{{.Names}}' | grep -qx "$n"; then
    docker rm -f "$n"
    echo "已停止: $n"
  fi
done

echo "完成（数据卷已保留）"
