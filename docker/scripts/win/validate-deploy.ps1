# Pre-deploy config check
# Usage:
#   docker\scripts\win\validate-deploy.cmd
#   docker\scripts\win\validate-deploy.cmd -Strict

param(
    [switch]$Strict
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$paths = Get-XlinkPaths
$distEnv = Join-Path $paths.DockerDir "env\distributed.env"
$issues = @()
$warnings = @()

function Read-DotEnvValue {
    param([string]$FilePath, [string]$Key)
    if (-not (Test-Path $FilePath)) { return $null }
    foreach ($line in Get-Content $FilePath) {
        $t = $line.Trim()
        if ($t -eq "" -or $t.StartsWith("#")) { continue }
        $idx = $t.IndexOf("=")
        if ($idx -lt 1) { continue }
        $k = $t.Substring(0, $idx).Trim()
        if ($k -eq $Key) {
            return $t.Substring($idx + 1).Trim()
        }
    }
    return $null
}

function Test-InsecureSecret {
    param([string]$Value)
    $insecure = @(
        "",
        "dev-local-secret-key-at-least-32-characters-long",
        "dev-flybook-internal-key-change-me",
        "change-me-in-production-use-a-long-random-string",
        "flybook-jwt-secret-change-in-production",
        "meeting-ai-jwt-secret-change-in-production",
        "root123",
        "app123",
        "admin123",
        "changeme",
        "secret",
        "change-me-on-first-run"
    )
    return $insecure -contains $Value
}

function Test-LocalUrl {
    param([string]$Value)
    if (-not $Value) { return $true }
    return ($Value -match "localhost") -or ($Value -match "127\.0\.0\.1")
}

$requiredFiles = @(
    @{ Path = $distEnv; Label = "docker\env\distributed.env" },
    @{ Path = (Join-Path $paths.RootDir "flybook\.env"); Label = "flybook\.env" },
    @{ Path = (Join-Path $paths.RootDir "meeting_ai\.env"); Label = "meeting_ai\.env" },
    @{ Path = (Join-Path $paths.RootDir "Information_Aggregation\backend\.env"); Label = "backend\.env" }
)
foreach ($f in $requiredFiles) {
    if (-not (Test-Path $f.Path)) {
        $issues += "Missing config file: $($f.Label)"
    }
}

if (-not (Test-Path $distEnv)) {
    Write-Host "ERROR: create docker\env\distributed.env first" -ForegroundColor Red
    exit 1
}

Import-XlinkEnv -EnvFile $distEnv

$appEnv = if ($env:APP_ENV) { $env:APP_ENV.Trim().ToLower() } else { "development" }

$backendEnv = Join-Path $paths.RootDir "Information_Aggregation\backend\.env"
$meetingEnv = Join-Path $paths.RootDir "meeting_ai\.env"
$flybookEnv = Join-Path $paths.RootDir "flybook\.env"

$backendSecret = Read-DotEnvValue $backendEnv "SECRET_KEY"
$flybookJwt = Read-DotEnvValue $flybookEnv "JWT_SECRET"
$meetingJwt = Read-DotEnvValue $meetingEnv "JWT_SECRET"
$jwt = $env:JWT_SECRET

$corsOrigins = $env:CORS_ORIGINS
if (-not $corsOrigins) {
    $corsOrigins = Read-DotEnvValue $flybookEnv "CORS_ORIGINS"
}
if (-not $corsOrigins) {
    $corsOrigins = Read-DotEnvValue $backendEnv "CORS_ORIGINS"
}

$portalFront = $env:PORTAL_FRONTEND_URL
if (-not $portalFront) {
    $portalFront = Read-DotEnvValue $flybookEnv "PORTAL_FRONTEND_URL"
}

$jwtCandidates = @($jwt, $backendSecret, $flybookJwt, $meetingJwt) | Where-Object { $_ }
$uniqueJwt = $jwtCandidates | Select-Object -Unique
if ($uniqueJwt.Count -gt 1) {
    $issues += "JWT mismatch: distributed JWT_SECRET must match backend SECRET_KEY and flybook/meeting JWT_SECRET"
}
if (Test-InsecureSecret $jwt) {
    $msg = "JWT_SECRET still uses default value in distributed.env"
    if ($appEnv -eq "production") { $issues += $msg } else { $warnings += $msg }
}

if (Test-InsecureSecret $env:PORTAL_INTERNAL_KEY) {
    $msg = "PORTAL_INTERNAL_KEY still uses default value"
    if ($appEnv -eq "production") { $issues += $msg } else { $warnings += $msg }
}

if (Test-InsecureSecret $env:MYSQL_ROOT_PASSWORD) {
    $msg = "MYSQL_ROOT_PASSWORD is weak"
    if ($appEnv -eq "production") { $issues += $msg } else { $warnings += $msg }
}
if (Test-InsecureSecret $env:MYSQL_PASSWORD) {
    $msg = "MYSQL_PASSWORD is weak"
    if ($appEnv -eq "production") { $issues += $msg } else { $warnings += $msg }
}

if (-not $corsOrigins -or $corsOrigins.Trim() -eq "") {
    if ($appEnv -eq "production") { $issues += "CORS_ORIGINS not set in flybook/.env or backend/.env" }
} elseif (Test-LocalUrl $corsOrigins) {
    if ($appEnv -eq "production") {
        $warnings += "CORS_ORIGINS has no public domain; browser access via cpolar/domain may fail"
    }
}

if (Test-LocalUrl $portalFront) {
    if ($appEnv -eq "production") {
        $warnings += "PORTAL_FRONTEND_URL is local; Feishu OAuth callback may fail"
    }
}

if ($appEnv -eq "production") {
    $feishuId = Read-DotEnvValue $flybookEnv "FEISHU_APP_ID"
    $feishuSecret = Read-DotEnvValue $flybookEnv "FEISHU_APP_SECRET"
    $feishuRedirect = Read-DotEnvValue $flybookEnv "FEISHU_OAUTH_REDIRECT_URI"
    if (-not $feishuId -or -not $feishuSecret) {
        $issues += "Set FEISHU_APP_ID and FEISHU_APP_SECRET in flybook/.env"
    }
    if (Test-LocalUrl $feishuRedirect) {
        $issues += "FEISHU_OAUTH_REDIRECT_URI must be a public URL in flybook/.env"
    }

    $llmProvider = Read-DotEnvValue $meetingEnv "LLM_PROVIDER"
    if (-not $llmProvider) { $llmProvider = "glm" }
    if ($llmProvider -eq "glm") {
        if (-not (Read-DotEnvValue $meetingEnv "GLM_API_KEY")) {
            $issues += "Set GLM_API_KEY in meeting_ai/.env"
        }
    }
    elseif ($llmProvider -eq "deepseek") {
        if (-not (Read-DotEnvValue $meetingEnv "DEEPSEEK_API_KEY")) {
            $issues += "Set DEEPSEEK_API_KEY in meeting_ai/.env"
        }
    }

    $tingwuKey = Read-DotEnvValue $meetingEnv "TINGWU_APP_KEY"
    $tingwuAk = Read-DotEnvValue $meetingEnv "ALIBABA_CLOUD_ACCESS_KEY_ID"
    if (-not $tingwuKey -or -not $tingwuAk) {
        $issues += "Set ALIBABA_CLOUD_ACCESS_KEY_ID and TINGWU_APP_KEY in meeting_ai/.env"
    }

    $adminPass = Read-DotEnvValue $backendEnv "ADMIN_PASSWORD"
    if (Test-InsecureSecret $adminPass) {
        $issues += "Change ADMIN_PASSWORD in backend/.env for production"
    }
}

try {
    Assert-DockerAvailable
    $imageNames = @("influencer-backend", "meeting-ai", "flybook", "portal-frontend")
    foreach ($img in $imageNames) {
        $full = Get-XlinkImage $img
        docker image inspect $full *> $null
        if ($LASTEXITCODE -ne 0) {
            $warnings += "Image not built: $full (run build-all first)"
        }
    }
}
catch {
    $warnings += "Docker not available; skipped image check"
}

Write-Host ""
$strictLabel = ""
if ($Strict) { $strictLabel = ", Strict" }
Write-Host "xlink deploy check (APP_ENV=$appEnv$strictLabel)"
Write-Host "distributed.env: $distEnv"
Write-Host ""

if ($warnings.Count -gt 0) {
    Write-Host "Warnings:" -ForegroundColor Yellow
    foreach ($w in $warnings) { Write-Host "  - $w" -ForegroundColor Yellow }
    Write-Host ""
}

if ($issues.Count -eq 0) {
    Write-Host "OK: no blocking issues found." -ForegroundColor Green
    exit 0
}

Write-Host "Issues:" -ForegroundColor Red
foreach ($i in $issues) { Write-Host "  - $i" -ForegroundColor Red }
Write-Host ""

if ($Strict -or $appEnv -eq "production") {
    exit 1
}

Write-Host "APP_ENV=development: issues are warnings only." -ForegroundColor Yellow
exit 0
