# 修复已有 MySQL 卷：授权 meeting_ai + 同步 app_user 密码（不删数据）
# 用法: .\docker\scripts\win\fix-mysql-grants.ps1

. "$PSScriptRoot\_common.ps1"
Import-XlinkEnv

$name = if ($env:MYSQL_CONTAINER_NAME) { $env:MYSQL_CONTAINER_NAME } else { "xlink_mysql" }
$user = if ($env:MYSQL_USER) { $env:MYSQL_USER } else { "app_user" }
$pass = if ($env:MYSQL_PASSWORD) { $env:MYSQL_PASSWORD } else { "app123" }
$rootPass = if ($env:MYSQL_ROOT_PASSWORD) { $env:MYSQL_ROOT_PASSWORD } else { "root123" }

$sql = @"
CREATE USER IF NOT EXISTS '$user'@'%' IDENTIFIED BY '$pass';
ALTER USER '$user'@'%' IDENTIFIED BY '$pass';
GRANT ALL PRIVILEGES ON influencer_db.* TO '$user'@'%';
GRANT ALL PRIVILEGES ON meeting_ai.* TO '$user'@'%';
FLUSH PRIVILEGES;
"@

docker exec -i $name mysql -uroot -p"$rootPass" -e $sql
Assert-DockerOk "fix mysql grants"

Write-Host "MySQL grants updated for $user@% (influencer_db + meeting_ai)"
