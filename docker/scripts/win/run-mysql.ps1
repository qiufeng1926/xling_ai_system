# 启动 MySQL
# 用法: .\docker\scripts\win\run-mysql.ps1

. "$PSScriptRoot\_common.ps1"
Import-XlinkEnv
$paths = Get-XlinkPaths

$net = Ensure-XlinkNetwork
$name = if ($env:MYSQL_CONTAINER_NAME) { $env:MYSQL_CONTAINER_NAME } else { "xlink_mysql" }
Stop-XlinkContainerIfExists $name

$port = if ($env:MYSQL_PORT) { $env:MYSQL_PORT } else { "3306" }
$dataVol = Get-VolumeArgs "mysql_data" "/var/lib/mysql"
$init1 = Join-Path $paths.RootDir "Information_Aggregation\scripts\init.sql"
$init2 = Join-Path $paths.RootDir "docker\mysql\02-meeting-ai.sql"
$init3 = Join-Path $paths.RootDir "docker\mysql\03-grants.sql"

docker run -d `
  --name $name `
  --restart unless-stopped `
  --network $net `
  -p "${port}:3306" `
  @dataVol `
  -v "${init1}:/docker-entrypoint-initdb.d/01-influencer.sql:ro" `
  -v "${init2}:/docker-entrypoint-initdb.d/02-meeting-ai.sql:ro" `
  -v "${init3}:/docker-entrypoint-initdb.d/03-grants.sql:ro" `
  -e "MYSQL_ROOT_PASSWORD=$($env:MYSQL_ROOT_PASSWORD)" `
  -e "MYSQL_DATABASE=influencer_db" `
  -e "MYSQL_USER=$($env:MYSQL_USER)" `
  -e "MYSQL_PASSWORD=$($env:MYSQL_PASSWORD)" `
  mysql:8.0 `
  --character-set-server=utf8mb4 `
  --collation-server=utf8mb4_unicode_ci
Assert-DockerOk "start MySQL ($name)"

Write-Host "MySQL started: $name (port $port)"
