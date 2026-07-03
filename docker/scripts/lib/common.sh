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

# 日志卷：默认绑定仓库内各服务 logs/（可用 LOGS_ROOT 覆盖）
logs_volume_mount() {
  local service_key="$1"
  local container_path="${2:-/app/logs}"
  local host_path
  case "$service_key" in
    meeting_ai) host_path="${ROOT_DIR}/meeting_ai/logs" ;;
    influencer_backend) host_path="${ROOT_DIR}/Information_Aggregation/backend/logs" ;;
    flybook) host_path="${ROOT_DIR}/flybook/logs" ;;
    *)
      echo "未知日志服务: $service_key" >&2
      exit 1
      ;;
  esac
  if [[ -n "${LOGS_ROOT:-}" ]]; then
    host_path="${LOGS_ROOT}/${service_key}"
  fi
  mkdir -p "$host_path"
  echo "-v" "$host_path:$container_path"
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

apply_build_defaults() {
  export PYTHON_BASE_IMAGE="${PYTHON_BASE_IMAGE:-docker.m.daocloud.io/library/python:3.11-slim}"
  export NODE_BASE_IMAGE="${NODE_BASE_IMAGE:-docker.m.daocloud.io/library/node:20-alpine}"
  export NGINX_BASE_IMAGE="${NGINX_BASE_IMAGE:-docker.m.daocloud.io/library/nginx:1.27-alpine}"
  export PIP_INDEX_URL="${PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple/}"
  export PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-mirrors.aliyun.com}"
  export NPM_REGISTRY="${NPM_REGISTRY:-https://registry.npmmirror.com}"
}

docker_build_args() {
  local args=()
  local key val
  for key in PYTHON_BASE_IMAGE NODE_BASE_IMAGE NGINX_BASE_IMAGE PLAYWRIGHT_BASE_IMAGE \
    PIP_INDEX_URL PIP_TRUSTED_HOST NPM_REGISTRY; do
    val="${!key:-}"
    if [[ -n "$val" ]]; then
      args+=(--build-arg "${key}=${val}")
    fi
  done
  echo "${args[@]}"
}
