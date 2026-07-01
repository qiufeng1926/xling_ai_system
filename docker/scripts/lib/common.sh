#!/usr/bin/env bash
# 公共函数：加载环境变量、镜像名、数据卷
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# lib/ -> scripts/ -> docker/
DOCKER_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROOT_DIR="$(cd "$DOCKER_DIR/.." && pwd)"

ENV_FILE="${ENV_FILE:-$DOCKER_DIR/env/distributed.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  echo "未找到环境文件: $ENV_FILE" >&2
  echo "请先执行: cp docker/env/distributed.env.example docker/env/distributed.env" >&2
  exit 1
fi

IMAGE_PREFIX="${IMAGE_PREFIX:-xlink}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

img() {
  echo "${IMAGE_PREFIX}/$1:${IMAGE_TAG}"
}

# 命名卷或绑定 DATA_ROOT 子目录
volume_mount() {
  local vol_name="$1"
  local container_path="$2"
  if [[ -n "${DATA_ROOT:-}" ]]; then
    local host_path="$DATA_ROOT/$vol_name"
    mkdir -p "$host_path"
    echo "-v" "$host_path:$container_path"
  else
    echo "-v" "$vol_name:$container_path"
  fi
}

ensure_network() {
  local net="${XLINK_NETWORK:-xlink_net}"
  if ! docker network inspect "$net" >/dev/null 2>&1; then
    docker network create "$net"
    echo "已创建 Docker 网络: $net"
  fi
  echo "$net"
}

stop_rm_if_exists() {
  local name="$1"
  if docker ps -a --format '{{.Names}}' | grep -qx "$name"; then
    docker rm -f "$name" >/dev/null
  fi
}
