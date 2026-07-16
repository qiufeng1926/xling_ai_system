# 修复已有 MySQL 卷：建库、同步 app_user 密码、授权（不删数据）
# 用法: docker\scripts\win\fix-mysql-grants.cmd

. "$PSScriptRoot\_common.ps1"
Import-XlinkEnv

$name = if ($env:MYSQL_CONTAINER_NAME) { $env:MYSQL_CONTAINER_NAME } else { "xlink_mysql" }
$user = if ($env:MYSQL_USER) { $env:MYSQL_USER } else { "app_user" }
$pass = if ($env:MYSQL_PASSWORD) { $env:MYSQL_PASSWORD } else { "app123" }
$rootPass = if ($env:MYSQL_ROOT_PASSWORD) { $env:MYSQL_ROOT_PASSWORD } else { "root123" }

$running = docker ps --format "{{.Names}}" | Select-String -Pattern "^$([regex]::Escape($name))$" -Quiet
if (-not $running) {
    throw "MySQL container '$name' is not running. Start it first: run-mysql.ps1"
}

$passSql = $pass.Replace("'", "''")
$userSql = $user.Replace("'", "''")

$sql = @"
CREATE DATABASE IF NOT EXISTS influencer_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS meeting_ai CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS xlink_agent CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$userSql'@'%' IDENTIFIED BY '$passSql';
CREATE USER IF NOT EXISTS '$userSql'@'localhost' IDENTIFIED BY '$passSql';
ALTER USER '$userSql'@'%' IDENTIFIED BY '$passSql';
ALTER USER '$userSql'@'localhost' IDENTIFIED BY '$passSql';
GRANT ALL PRIVILEGES ON influencer_db.* TO '$userSql'@'%';
GRANT ALL PRIVILEGES ON meeting_ai.* TO '$userSql'@'%';
GRANT ALL PRIVILEGES ON xlink_agent.* TO '$userSql'@'%';
GRANT ALL PRIVILEGES ON influencer_db.* TO '$userSql'@'localhost';
GRANT ALL PRIVILEGES ON meeting_ai.* TO '$userSql'@'localhost';
GRANT ALL PRIVILEGES ON xlink_agent.* TO '$userSql'@'localhost';
FLUSH PRIVILEGES;
"@

$sql | docker exec -i $name mysql -uroot -p"$rootPass"
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: root login failed. MYSQL_ROOT_PASSWORD in docker\env\distributed.env" -ForegroundColor Red
    Write-Host "       may not match the password used when this MySQL volume was first created." -ForegroundColor Red
    exit 1
}

Write-Host "OK: $user @ $name (influencer_db + meeting_ai + xlink_agent)"
