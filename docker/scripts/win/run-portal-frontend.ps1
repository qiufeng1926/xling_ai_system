# 启动门户前端 :80
# 用法: .\docker\scripts\win\run-portal-frontend.ps1

. "$PSScriptRoot\_common.ps1"
Import-XlinkEnv

$net = Ensure-XlinkNetwork
$name = if ($env:PORTAL_CONTAINER_NAME) { $env:PORTAL_CONTAINER_NAME } else { "xlink_portal_frontend" }
Stop-XlinkContainerIfExists $name

$port = if ($env:PORTAL_HTTP_PORT) { $env:PORTAL_HTTP_PORT } else { "80" }
$infHost = if ($env:INFLUENCER_API_HOST) { $env:INFLUENCER_API_HOST } else { "xlink_influencer_backend" }
$meetHost = if ($env:MEETING_API_HOST) { $env:MEETING_API_HOST } else { "xlink_meeting_ai" }
$flyHost = if ($env:FLYBOOK_API_HOST) { $env:FLYBOOK_API_HOST } else { "xlink_flybook" }
$infPort = if ($env:INFLUENCER_API_PORT) { $env:INFLUENCER_API_PORT } else { "8000" }
$meetPort = if ($env:MEETING_API_PORT) { $env:MEETING_API_PORT } else { "8001" }
$flyPort = if ($env:FLYBOOK_API_PORT) { $env:FLYBOOK_API_PORT } else { "8002" }

docker run -d `
  --name $name `
  --restart unless-stopped `
  --network $net `
  -p "${port}:80" `
  -e "INFLUENCER_API_HOST=${infHost}:${infPort}" `
  -e "MEETING_API_HOST=${meetHost}:${meetPort}" `
  -e "FLYBOOK_API_HOST=${flyHost}:${flyPort}" `
  (Get-XlinkImage "portal-frontend")

Write-Host "门户前端已启动: $name (端口 $port)"
