# 启动达人后端 :8000
# 用法: .\docker\scripts\win\run-influencer-backend.ps1

. "$PSScriptRoot\_common.ps1"
Import-XlinkEnv

$net = Ensure-XlinkNetwork
$name = if ($env:INFLUENCER_CONTAINER_NAME) { $env:INFLUENCER_CONTAINER_NAME } else { "xlink_influencer_backend" }
Stop-XlinkContainerIfExists $name

$logsVol = Get-VolumeArgs "influencer_logs" "/app/logs"
$cookiesVol = Get-VolumeArgs "influencer_cookies" "/app/cookies"
$port = if ($env:INFLUENCER_API_PORT) { $env:INFLUENCER_API_PORT } else { "8000" }
$adminUser = if ($env:ADMIN_USERNAME) { $env:ADMIN_USERNAME } else { "admin" }
$adminPass = if ($env:ADMIN_PASSWORD) { $env:ADMIN_PASSWORD } else { "admin123" }

docker run -d `
  --name $name `
  --restart unless-stopped `
  --network $net `
  -p "${port}:8000" `
  @logsVol @cookiesVol `
  -e "DB_HOST=$($env:DB_HOST)" `
  -e "DB_PORT=$($env:DB_PORT)" `
  -e "DB_USER=$($env:MYSQL_USER)" `
  -e "DB_PASSWORD=$($env:MYSQL_PASSWORD)" `
  -e "DB_NAME=influencer_db" `
  -e "REDIS_URL=$($env:REDIS_URL)" `
  -e "SECRET_KEY=$($env:JWT_SECRET)" `
  -e "DEBUG=$($env:DEBUG)" `
  -e "API_HOST=0.0.0.0" `
  -e "API_PORT=8000" `
  -e "CORS_ORIGINS=$($env:CORS_ORIGINS)" `
  -e "FLYBOOK_API_URL=$($env:FLYBOOK_API_URL)" `
  -e "MEETING_AI_API_URL=$($env:MEETING_AI_API_URL)" `
  -e "PORTAL_INTERNAL_KEY=$($env:PORTAL_INTERNAL_KEY)" `
  -e "FLYBOOK_INTERNAL_KEY=$($env:PORTAL_INTERNAL_KEY)" `
  -e "ADMIN_USERNAME=$adminUser" `
  -e "ADMIN_PASSWORD=$adminPass" `
  (Get-XlinkImage "influencer-backend")
Assert-DockerOk "start influencer backend ($name)"

Write-Host "Influencer backend started: $name (port $port)"
