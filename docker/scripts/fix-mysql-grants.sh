#!/usr/bin/env bash
# 修复已有 MySQL 卷：授权 meeting_ai + 同步 app_user 密码（不删数据）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

NAME="${MYSQL_CONTAINER_NAME:-xlink_mysql}"
USER="${MYSQL_USER:-app_user}"
PASS="${MYSQL_PASSWORD:-app123}"
ROOT_PASS="${MYSQL_ROOT_PASSWORD:-root123}"

if ! docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
  echo "MySQL 容器未运行: $NAME（请先 run-mysql.sh）" >&2
  exit 1
fi

SQL="
CREATE DATABASE IF NOT EXISTS influencer_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS meeting_ai CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${USER}'@'%' IDENTIFIED BY '${PASS}';
CREATE USER IF NOT EXISTS '${USER}'@'localhost' IDENTIFIED BY '${PASS}';
ALTER USER '${USER}'@'%' IDENTIFIED BY '${PASS}';
ALTER USER '${USER}'@'localhost' IDENTIFIED BY '${PASS}';
GRANT ALL PRIVILEGES ON influencer_db.* TO '${USER}'@'%';
GRANT ALL PRIVILEGES ON meeting_ai.* TO '${USER}'@'%';
GRANT ALL PRIVILEGES ON influencer_db.* TO '${USER}'@'localhost';
GRANT ALL PRIVILEGES ON meeting_ai.* TO '${USER}'@'localhost';
FLUSH PRIVILEGES;
"

if ! docker exec -i "$NAME" mysql -uroot -p"$ROOT_PASS" -e "$SQL"; then
  echo "" >&2
  echo "ERROR: root 登录失败。distributed.env 中 MYSQL_ROOT_PASSWORD 可能与数据卷初始化时不一致。" >&2
  echo "可尝试恢复当初 root 密码，或清空卷后重建（会丢数据）。" >&2
  exit 1
fi

echo "OK: ${USER} @ ${NAME}（influencer_db + meeting_ai）"
