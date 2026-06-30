# 按顺序启动全部服务（已构建镜像）
# 用法: .\docker\scripts\win\run-all.ps1

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
& "$dir\run-mysql.ps1"
Write-Host "等待 MySQL 就绪..."
Start-Sleep -Seconds 15
& "$dir\run-redis.ps1"
& "$dir\run-influencer-backend.ps1"
Start-Sleep -Seconds 3
& "$dir\run-meeting-ai.ps1"
& "$dir\run-flybook.ps1"
& "$dir\run-portal-frontend.ps1"
Write-Host "`n全部服务已启动"
