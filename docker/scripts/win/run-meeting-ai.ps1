# 启动会议 AI :8001
# 用法: .\docker\scripts\win\run-meeting-ai.ps1

. "$PSScriptRoot\_common.ps1"
Import-XlinkEnv

$net = Ensure-XlinkNetwork
$name = if ($env:MEETING_CONTAINER_NAME) { $env:MEETING_CONTAINER_NAME } else { "xlink_meeting_ai" }
Stop-XlinkContainerIfExists $name

$uploadVol = Get-VolumeArgs "meeting_upload" "/app/upload"
$outputVol = Get-VolumeArgs "meeting_output" "/app/output"
$logsVol = Get-VolumeArgs "meeting_logs" "/app/logs"
$port = if ($env:MEETING_API_PORT) { $env:MEETING_API_PORT } else { "8001" }

docker run -d `
  --name $name `
  --restart unless-stopped `
  --network $net `
  -p "${port}:8001" `
  @uploadVol @outputVol @logsVol `
  -e "APP_ENV=$($env:APP_ENV)" `
  -e "JWT_SECRET=$($env:JWT_SECRET)" `
  -e "PORTAL_API_URL=$($env:INFLUENCER_API_URL)" `
  -e "PORTAL_INTERNAL_KEY=$($env:PORTAL_INTERNAL_KEY)" `
  -e "CORS_ORIGINS=$($env:CORS_ORIGINS)" `
  -e "DB_HOST=$($env:DB_HOST)" `
  -e "DB_PORT=$($env:DB_PORT)" `
  -e "DB_USER=$($env:MYSQL_USER)" `
  -e "DB_PASSWORD=$($env:MYSQL_PASSWORD)" `
  -e "DB_NAME=meeting_ai" `
  -e "LLM_PROVIDER=$($env:LLM_PROVIDER)" `
  -e "GLM_API_KEY=$($env:GLM_API_KEY)" `
  -e "GLM_MODEL=$($env:GLM_MODEL)" `
  -e "ALIBABA_CLOUD_ACCESS_KEY_ID=$($env:ALIBABA_CLOUD_ACCESS_KEY_ID)" `
  -e "ALIBABA_CLOUD_ACCESS_KEY_SECRET=$($env:ALIBABA_CLOUD_ACCESS_KEY_SECRET)" `
  -e "TINGWU_APP_KEY=$($env:TINGWU_APP_KEY)" `
  -e "TINGWU_REGION=$($env:TINGWU_REGION)" `
  -e "TINGWU_DOMAIN=$($env:TINGWU_DOMAIN)" `
  -e "MAX_UPLOAD_BYTES=$($env:MAX_UPLOAD_BYTES)" `
  (Get-XlinkImage "meeting-ai")

Write-Host "会议 AI 已启动: $name (端口 $port)"
