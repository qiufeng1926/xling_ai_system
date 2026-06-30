# 启动 Redis
# 用法: .\docker\scripts\win\run-redis.ps1

. "$PSScriptRoot\_common.ps1"
Import-XlinkEnv

$net = Ensure-XlinkNetwork
$name = if ($env:REDIS_CONTAINER_NAME) { $env:REDIS_CONTAINER_NAME } else { "xlink_redis" }
Stop-XlinkContainerIfExists $name
$port = if ($env:REDIS_PORT) { $env:REDIS_PORT } else { "6379" }

docker run -d `
  --name $name `
  --restart unless-stopped `
  --network $net `
  -p "${port}:6379" `
  redis:7-alpine

Write-Host "Redis 已启动: $name (端口 $port)"
