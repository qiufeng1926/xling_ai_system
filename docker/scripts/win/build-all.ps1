# Build all xlink images
# Usage: .\docker\scripts\win\build-all.ps1

. "$PSScriptRoot\_common.ps1"

try {
# 启动前可选检查（development 仅警告，production 须 -Strict）
# docker\scripts\win\validate-deploy.cmd

    Assert-DockerAvailable
    Import-XlinkEnv -Optional
    Set-XlinkBuildDefaults

    $paths = Get-XlinkPaths
    $root = $paths.RootDir
    Write-Host "Root: $root"
    Write-Host "Images: $($env:IMAGE_PREFIX)/*:$($env:IMAGE_TAG)"
    Write-Host "Python base: $($env:PYTHON_BASE_IMAGE)"
    Write-Host "Node base:   $($env:NODE_BASE_IMAGE)"
    Write-Host "Nginx base:  $($env:NGINX_BASE_IMAGE)"
    if ($env:PIP_INDEX_URL) { Write-Host "Pip index:   $($env:PIP_INDEX_URL)" }
    Write-Host ""

    function Build-XlinkImage {
        param(
            [string]$Label,
            [string]$ImageName,
            [string]$Context
        )
        $tag = Get-XlinkImage $ImageName
        $ctx = Join-Path $root $Context
        if (-not (Test-Path $ctx)) {
            throw "Build context not found: $ctx"
        }
        Write-Host "==> Building $Label ($tag) ..."
        $buildArgs = Get-DockerBuildArgs
        docker build @buildArgs -t $tag $ctx
        if ($LASTEXITCODE -ne 0) {
            throw "docker build failed: $tag"
        }
        Write-Host ""
    }

    Build-XlinkImage "influencer-backend" "influencer-backend" "Information_Aggregation\backend"
    Build-XlinkImage "meeting-ai" "meeting-ai" "meeting_ai"
    Build-XlinkImage "flybook" "flybook" "flybook"
    Build-XlinkImage "portal-frontend" "portal-frontend" "Information_Aggregation\frontend"

    Write-Host "Done. Images:"
    docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | Select-String "xlink"
}
catch {
    Write-Host ""
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Tip: if base image pull still fails, set registry mirror in Docker Desktop:" -ForegroundColor Yellow
    Write-Host '  Settings -> Docker Engine -> "registry-mirrors": ["https://docker.m.daocloud.io"]' -ForegroundColor Yellow
    exit 1
}
