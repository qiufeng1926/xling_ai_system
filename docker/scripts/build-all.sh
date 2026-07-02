#!/usr/bin/env bash
# 构建全部 xlink 镜像（在仓库根目录执行）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

docker_build_args() {
  local args=()
  if [[ -n "${PIP_INDEX_URL:-}" ]]; then
    args+=(--build-arg "PIP_INDEX_URL=$PIP_INDEX_URL")
  fi
  if [[ -n "${PIP_TRUSTED_HOST:-}" ]]; then
    args+=(--build-arg "PIP_TRUSTED_HOST=$PIP_TRUSTED_HOST")
  fi
  if [[ -n "${NPM_REGISTRY:-}" ]]; then
    args+=(--build-arg "NPM_REGISTRY=$NPM_REGISTRY")
  fi
  echo "${args[@]}"
}

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
