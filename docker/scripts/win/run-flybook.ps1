# 启动飞书后端 :8002
# 用法: .\docker\scripts\win\run-flybook.ps1

. "$PSScriptRoot\_common.ps1"
Import-XlinkEnv

$net = Ensure-XlinkNetwork
$name = if ($env:FLYBOOK_CONTAINER_NAME) { $env:FLYBOOK_CONTAINER_NAME } else { "xlink_flybook" }
Stop-XlinkContainerIfExists $name

$logsVol = Get-VolumeArgs "flybook_logs" "/app/logs"
$port = if ($env:FLYBOOK_API_PORT) { $env:FLYBOOK_API_PORT } else { "8002" }

docker run -d `
  --name $name `
  --restart unless-stopped `
  --network $net `
  -p "${port}:8002" `
  @logsVol `
  -e "APP_ENV=$($env:APP_ENV)" `
  -e "JWT_SECRET=$($env:JWT_SECRET)" `
  -e "PORTAL_API_URL=$($env:INFLUENCER_API_URL)" `
  -e "PORTAL_FRONTEND_URL=$($env:PORTAL_FRONTEND_URL)" `
  -e "FLYBOOK_INTERNAL_KEY=$($env:PORTAL_INTERNAL_KEY)" `
  -e "CORS_ORIGINS=$($env:CORS_ORIGINS)" `
  -e "FEISHU_APP_ID=$($env:FEISHU_APP_ID)" `
  -e "FEISHU_APP_SECRET=$($env:FEISHU_APP_SECRET)" `
  -e "FEISHU_OAUTH_REDIRECT_URI=$($env:FEISHU_OAUTH_REDIRECT_URI)" `
  -e "FEISHU_VERIFICATION_TOKEN=$($env:FEISHU_VERIFICATION_TOKEN)" `
  -e "FEISHU_ENCRYPT_KEY=$($env:FEISHU_ENCRYPT_KEY)" `
  -e "FEISHU_MESSENGER_URL=$($env:FEISHU_MESSENGER_URL)" `
  (Get-XlinkImage "flybook")

Write-Host "飞书后端已启动: $name (端口 $port)"
