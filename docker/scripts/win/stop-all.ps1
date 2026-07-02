# Stop all xlink containers (keep volumes)
# Usage: docker\scripts\win\stop-all.cmd

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

try {
    Assert-DockerAvailable

    $names = @(
        "xlink_portal_frontend",
        "xlink_flybook",
        "xlink_meeting_ai",
        "xlink_influencer_backend",
        "xlink_redis",
        "xlink_mysql"
    )

    foreach ($n in $names) {
        $exists = docker ps -a --format "{{.Names}}" | Select-String -Pattern "^$([regex]::Escape($n))$" -Quiet
        if ($exists) {
            docker rm -f $n | Out-Null
            Assert-DockerOk "stop $n"
            Write-Host "Stopped: $n"
        }
    }
    Write-Host "Done."
}
catch {
    Write-Host ""
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
