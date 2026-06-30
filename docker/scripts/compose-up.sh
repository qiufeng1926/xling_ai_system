#!/usr/bin/env bash
# 单机 Compose 全栈启动（含 MySQL / Redis / 三后端 / 前端）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_ENV="${COMPOSE_ENV:-$ROOT_DIR/docker/.env}"

if [[ ! -f "$COMPOSE_ENV" ]]; then
  cp "$ROOT_DIR/docker/.env.example" "$COMPOSE_ENV"
  echo "已生成 $COMPOSE_ENV ，请修改后重新运行"
  exit 1
fi

cd "$ROOT_DIR"
docker compose --env-file "$COMPOSE_ENV" up -d --build "$@"
echo "Compose 已启动。门户: http://localhost:${PORTAL_HTTP_PORT:-80}"
