# 启动飞书后端 :8002（读取 flybook/.env，基础设施地址来自 distributed.env）
# 用法: .\docker\scripts\win\run-flybook.ps1

. "$PSScriptRoot\_common.ps1"
Import-XlinkEnv

$paths = Get-XlinkPaths
$net = Ensure-XlinkNetwork
$name = if ($env:FLYBOOK_CONTAINER_NAME) { $env:FLYBOOK_CONTAINER_NAME } else { "xlink_flybook" }
Stop-XlinkContainerIfExists $name

$logsVol = Get-LogsVolumeArgs "flybook"
$port = if ($env:FLYBOOK_API_PORT) { $env:FLYBOOK_API_PORT } else { "8002" }

$serviceEnv = Get-ServiceEnvFileArgs "flybook\.env"
$portalUrl = if ($env:INFLUENCER_API_URL) { $env:INFLUENCER_API_URL } else { "http://xlink_influencer_backend:8000" }
$portalFront = if ($env:PORTAL_FRONTEND_URL) { $env:PORTAL_FRONTEND_URL } else { "http://127.0.0.1" }
$internalKey = if ($env:PORTAL_INTERNAL_KEY) { $env:PORTAL_INTERNAL_KEY } else { "dev-flybook-internal-key-change-me" }
$cors = if ($env:CORS_ORIGINS) { $env:CORS_ORIGINS } else { "http://127.0.0.1,http://localhost" }
# 镜像曾默认 production 会强制校验飞书密钥；本地/内网 Docker 部署用 development
$appEnv = if ($env:APP_ENV) { $env:APP_ENV } else { "development" }

docker run -d `
  --name $name `
  --restart unless-stopped `
  --network $net `
  -p "${port}:8002" `
  @logsVol `
  @serviceEnv `
  -e "APP_ENV=$appEnv" `
  -e "JWT_SECRET=$($env:JWT_SECRET)" `
  -e "PORTAL_API_URL=$portalUrl" `
  -e "PORTAL_FRONTEND_URL=$portalFront" `
  -e "FLYBOOK_INTERNAL_KEY=$internalKey" `
  -e "CORS_ORIGINS=$cors" `
  (Get-XlinkImage "flybook")
Assert-DockerOk "start flybook ($name)"

Write-Host "Flybook started: $name (port $port)"
Write-Host "Config: flybook\.env + distributed.env (service URLs)"
$logPath = if ($env:LOGS_ROOT) { Join-Path $env:LOGS_ROOT "flybook" } else { Join-Path $paths.RootDir "flybook\logs" }
Write-Host "Logs: $logPath"
