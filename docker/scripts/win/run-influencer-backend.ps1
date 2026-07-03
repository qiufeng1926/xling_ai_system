# 启动达人后端 :8000（读取 backend/.env，基础设施地址来自 distributed.env）
# 用法: .\docker\scripts\win\run-influencer-backend.ps1

. "$PSScriptRoot\_common.ps1"
Import-XlinkEnv

$paths = Get-XlinkPaths
$net = Ensure-XlinkNetwork
$name = if ($env:INFLUENCER_CONTAINER_NAME) { $env:INFLUENCER_CONTAINER_NAME } else { "xlink_influencer_backend" }
Stop-XlinkContainerIfExists $name

$logsVol = Get-LogsVolumeArgs "influencer_backend"
$cookiesVol = Get-VolumeArgs "influencer_cookies" "/app/cookies"
$port = if ($env:INFLUENCER_API_PORT) { $env:INFLUENCER_API_PORT } else { "8000" }

$serviceEnv = Get-ServiceEnvFileArgs "Information_Aggregation\backend\.env"
$dbOverrides = Get-DbInfraOverrides "influencer_db"
$redisUrl = if ($env:REDIS_URL) { $env:REDIS_URL } else { "redis://xlink_redis:6379/0" }
$flybookUrl = if ($env:FLYBOOK_API_URL) { $env:FLYBOOK_API_URL } else { "http://xlink_flybook:8002" }
$meetingUrl = if ($env:MEETING_AI_API_URL) { $env:MEETING_AI_API_URL } else { "http://xlink_meeting_ai:8001" }
$internalKey = if ($env:PORTAL_INTERNAL_KEY) { $env:PORTAL_INTERNAL_KEY } else { "dev-flybook-internal-key-change-me" }
$cors = if ($env:CORS_ORIGINS) { $env:CORS_ORIGINS } else { "http://127.0.0.1,http://localhost" }

docker run -d `
  --name $name `
  --restart unless-stopped `
  --network $net `
  -p "${port}:8000" `
  @logsVol @cookiesVol `
  @serviceEnv `
  @dbOverrides `
  -e "REDIS_URL=$redisUrl" `
  -e "SECRET_KEY=$($env:JWT_SECRET)" `
  -e "API_HOST=0.0.0.0" `
  -e "API_PORT=8000" `
  -e "CORS_ORIGINS=$cors" `
  -e "FLYBOOK_API_URL=$flybookUrl" `
  -e "MEETING_AI_API_URL=$meetingUrl" `
  -e "PORTAL_INTERNAL_KEY=$internalKey" `
  -e "FLYBOOK_INTERNAL_KEY=$internalKey" `
  (Get-XlinkImage "influencer-backend")
Assert-DockerOk "start influencer backend ($name)"

Write-Host "Influencer backend started: $name (port $port)"
Write-Host "Config: Information_Aggregation\backend\.env + distributed.env (DB/Redis)"
$logPath = if ($env:LOGS_ROOT) { Join-Path $env:LOGS_ROOT "influencer_backend" } else { Join-Path $paths.RootDir "Information_Aggregation\backend\logs" }
Write-Host "Logs: $logPath"
