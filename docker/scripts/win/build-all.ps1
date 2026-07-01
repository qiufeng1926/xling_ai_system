# Build all xlink images
# Usage: .\docker\scripts\win\build-all.ps1

. "$PSScriptRoot\_common.ps1"

try {
    Assert-DockerAvailable
    Import-XlinkEnv -Optional

    $paths = Get-XlinkPaths
    $root = $paths.RootDir
    Write-Host "Root: $root"
    Write-Host "Images: $($env:IMAGE_PREFIX)/*:$($env:IMAGE_TAG)"
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
        docker build -t $tag $ctx
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
    exit 1
}
