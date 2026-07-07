#!/usr/bin/env bash
# 按依赖顺序启动全部服务（单机分布式 / 已构建镜像）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$SCRIPT_DIR/run-mysql.sh"
echo "等待 MySQL 就绪..."
sleep 15
bash "$SCRIPT_DIR/fix-mysql-grants.sh"

bash "$SCRIPT_DIR/run-redis.sh"
bash "$SCRIPT_DIR/run-influencer-backend.sh"
sleep 3
bash "$SCRIPT_DIR/run-meeting-ai.sh"
sleep 20
if ! docker exec xlink_meeting_ai curl -fsS http://127.0.0.1:8001/health >/dev/null 2>&1; then
  echo "WARNING: meeting-ai 健康检查失败，请查看: docker logs xlink_meeting_ai" >&2
fi
bash "$SCRIPT_DIR/run-flybook.sh"
bash "$SCRIPT_DIR/run-portal-frontend.sh"

echo ""
echo "全部服务已启动。访问门户: http://127.0.0.1:${PORTAL_HTTP_PORT:-80}"
