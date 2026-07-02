#!/usr/bin/env bash
# 构建全部 xlink 镜像（在仓库根目录执行）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

apply_build_defaults

echo "Python base: $PYTHON_BASE_IMAGE"
echo "Node base:   $NODE_BASE_IMAGE"
echo "Nginx base:  $NGINX_BASE_IMAGE"
echo ""

echo "==> 构建达人后端..."
docker build $(docker_build_args) -t "$(img influencer-backend)" "$ROOT_DIR/Information_Aggregation/backend"

echo "==> 构建会议 AI..."
docker build $(docker_build_args) -t "$(img meeting-ai)" "$ROOT_DIR/meeting_ai"

echo "==> 构建飞书后端..."
docker build $(docker_build_args) -t "$(img flybook)" "$ROOT_DIR/flybook"

echo "==> 构建门户前端..."
docker build $(docker_build_args) -t "$(img portal-frontend)" "$ROOT_DIR/Information_Aggregation/frontend"

echo ""
echo "全部镜像构建完成:"
docker images --format '  {{.Repository}}:{{.Tag}}' | grep "^  ${IMAGE_PREFIX}/" || true
