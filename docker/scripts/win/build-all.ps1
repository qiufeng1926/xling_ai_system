# 构建全部 xlink 镜像
# 用法: .\docker\scripts\win\build-all.ps1

. "$PSScriptRoot\_common.ps1"
Import-XlinkEnv

$paths = Get-XlinkPaths
$root = $paths.RootDir

Write-Host "==> 构建达人后端..."
docker build -t (Get-XlinkImage "influencer-backend") "$root\Information_Aggregation\backend"

Write-Host "==> 构建会议 AI..."
docker build -t (Get-XlinkImage "meeting-ai") "$root\meeting_ai"

Write-Host "==> 构建飞书后端..."
docker build -t (Get-XlinkImage "flybook") "$root\flybook"

Write-Host "==> 构建门户前端..."
docker build -t (Get-XlinkImage "portal-frontend") "$root\Information_Aggregation\frontend"

Write-Host "`n全部镜像构建完成"
