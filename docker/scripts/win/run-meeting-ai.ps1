# 启动会议 AI :8001（读取 meeting_ai/.env，基础设施地址来自 distributed.env）
# 用法: .\docker\scripts\win\run-meeting-ai.ps1

. "$PSScriptRoot\_common.ps1"
Import-XlinkEnv

$paths = Get-XlinkPaths
$net = Ensure-XlinkNetwork
$name = if ($env:MEETING_CONTAINER_NAME) { $env:MEETING_CONTAINER_NAME } else { "xlink_meeting_ai" }
Stop-XlinkContainerIfExists $name

$uploadVol = Get-VolumeArgs "meeting_upload" "/app/upload"
$outputVol = Get-VolumeArgs "meeting_output" "/app/output"
$logsVol = Get-LogsVolumeArgs "meeting_ai"
$port = if ($env:MEETING_API_PORT) { $env:MEETING_API_PORT } else { "8001" }

$serviceEnv = Get-ServiceEnvFileArgs "meeting_ai\.env"
$dbOverrides = Get-DbInfraOverrides "meeting_ai"
$portalUrl = if ($env:INFLUENCER_API_URL) { $env:INFLUENCER_API_URL } else { "http://xlink_influencer_backend:8000" }
$internalKey = if ($env:PORTAL_INTERNAL_KEY) { $env:PORTAL_INTERNAL_KEY } else { "dev-flybook-internal-key-change-me" }
$cors = if ($env:CORS_ORIGINS) { $env:CORS_ORIGINS } else { "http://127.0.0.1,http://localhost" }

docker run -d `
  --name $name `
  --restart unless-stopped `
  --network $net `
  -p "${port}:8001" `
  @uploadVol @outputVol @logsVol `
  @serviceEnv `
  @dbOverrides `
  -e "PORTAL_API_URL=$portalUrl" `
  -e "PORTAL_INTERNAL_KEY=$internalKey" `
  -e "CORS_ORIGINS=$cors" `
  (Get-XlinkImage "meeting-ai")
Assert-DockerOk "start meeting-ai ($name)"

Write-Host "Meeting AI started: $name (port $port)"
Write-Host "Config: meeting_ai\.env + docker\env\distributed.env (DB_HOST only)"
$logPath = if ($env:LOGS_ROOT) { Join-Path $env:LOGS_ROOT "meeting_ai" } else { Join-Path $paths.RootDir "meeting_ai\logs" }
Write-Host "Logs: $logPath"
