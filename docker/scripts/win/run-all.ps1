# Start all xlink services (docker run)
# Usage: docker\scripts\win\run-all.cmd

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

function Invoke-XlinkStep {
    param(
        [string]$ScriptName,
        [string]$Label
    )
    $scriptPath = Join-Path $PSScriptRoot $ScriptName
    if (-not (Test-Path $scriptPath)) {
        throw "Script not found: $scriptPath"
    }
    Write-Host ""
    Write-Host "==> $Label"
    & $scriptPath
}

try {
    Assert-DockerAvailable
    Import-XlinkEnv

    $paths = Get-XlinkPaths
    Write-Host "Root: $($paths.RootDir)"
    Write-Host "Env:  $(Join-Path $paths.DockerDir 'env\distributed.env')"
    Write-Host "Images: $($env:IMAGE_PREFIX)/*:$($env:IMAGE_TAG)"

    Invoke-XlinkStep "run-mysql.ps1" "MySQL"
    Write-Host "Waiting for MySQL (15s)..."
    Start-Sleep -Seconds 15

    Invoke-XlinkStep "run-redis.ps1" "Redis"
    Invoke-XlinkStep "run-influencer-backend.ps1" "Influencer backend :8000"
    Write-Host "Waiting for influencer backend (3s)..."
    Start-Sleep -Seconds 3

    Invoke-XlinkStep "run-meeting-ai.ps1" "Meeting AI :8001"
    Start-Sleep -Seconds 20
    $meetOk = docker exec xlink_meeting_ai curl -fsS http://127.0.0.1:8001/health 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARNING: meeting-ai health check failed. Run: docker logs xlink_meeting_ai" -ForegroundColor Yellow
    }
    Invoke-XlinkStep "run-flybook.ps1" "Flybook :8002"
    Invoke-XlinkStep "run-portal-frontend.ps1" "Portal frontend :80"

    Write-Host ""
    Write-Host "All services started:"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | Select-String "xlink"
    Write-Host ""
    Write-Host "Portal: http://127.0.0.1:$($env:PORTAL_HTTP_PORT)"
    Write-Host ""
    Write-Host "Logs (host bind mounts):"
    if ($env:LOGS_ROOT) {
        Write-Host "  meeting_ai:           $(Join-Path $env:LOGS_ROOT 'meeting_ai')"
        Write-Host "  influencer_backend:   $(Join-Path $env:LOGS_ROOT 'influencer_backend')"
        Write-Host "  flybook:              $(Join-Path $env:LOGS_ROOT 'flybook')"
    }
    else {
        Write-Host "  meeting_ai:           $(Join-Path $paths.RootDir 'meeting_ai\logs')"
        Write-Host "  influencer_backend:   $(Join-Path $paths.RootDir 'Information_Aggregation\backend\logs')"
        Write-Host "  flybook:              $(Join-Path $paths.RootDir 'flybook\logs')"
    }
}
catch {
    Write-Host ""
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Tip: use docker\scripts\win\run-all.cmd from CMD" -ForegroundColor Yellow
    exit 1
}
