# xlink Docker scripts (Windows PowerShell)
# Env file default: docker\env\distributed.env

$ErrorActionPreference = "Stop"
$script:XlinkWinDir = $PSScriptRoot

function Get-XlinkPaths {
  # win/ -> scripts/ -> docker/ -> repo root
  $ScriptDir = $script:XlinkWinDir
  $DockerDir = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
  $RootDir = (Resolve-Path (Join-Path $DockerDir "..")).Path
  return @{ ScriptDir = $ScriptDir; DockerDir = $DockerDir; RootDir = $RootDir }
}

function Import-XlinkEnv {
    param(
        [string]$EnvFile,
        [switch]$Optional
    )
    $paths = Get-XlinkPaths
    if (-not $EnvFile) {
        $EnvFile = Join-Path $paths.DockerDir "env\distributed.env"
    }
    if (-not (Test-Path $EnvFile)) {
        $example = Join-Path $paths.DockerDir "env\distributed.env.example"
        if ((-not $Optional) -and (Test-Path $example)) {
            Copy-Item $example $EnvFile
            Write-Host "Created env from template: $EnvFile" -ForegroundColor Yellow
            Write-Host "WARNING: Using example defaults. Edit before production deploy." -ForegroundColor Yellow
        }
        elseif (-not $Optional) {
            throw "Missing $EnvFile. Run: copy `"$example`" `"$EnvFile`""
        }
        else {
            if (-not $env:IMAGE_PREFIX) { $env:IMAGE_PREFIX = "xlink" }
            if (-not $env:IMAGE_TAG) { $env:IMAGE_TAG = "latest" }
            return
        }
    }
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq "" -or $line.StartsWith("#")) { return }
        $idx = $line.IndexOf("=")
        if ($idx -lt 1) { return }
        $key = $line.Substring(0, $idx).Trim()
        $val = $line.Substring($idx + 1).Trim()
        Set-Item -Path "env:$key" -Value $val
    }
    if (-not $env:IMAGE_PREFIX) { $env:IMAGE_PREFIX = "xlink" }
    if (-not $env:IMAGE_TAG) { $env:IMAGE_TAG = "latest" }
}

function Set-XlinkBuildDefaults {
    # Docker Hub 在国内常超时，构建脚本默认走 DaoCloud 镜像加速
    if (-not $env:PYTHON_BASE_IMAGE) {
        $env:PYTHON_BASE_IMAGE = "docker.m.daocloud.io/library/python:3.11-slim"
    }
    if (-not $env:NODE_BASE_IMAGE) {
        $env:NODE_BASE_IMAGE = "docker.m.daocloud.io/library/node:20-alpine"
    }
    if (-not $env:NGINX_BASE_IMAGE) {
        $env:NGINX_BASE_IMAGE = "docker.m.daocloud.io/library/nginx:1.27-alpine"
    }
    if (-not $env:PIP_INDEX_URL) {
        $env:PIP_INDEX_URL = "https://mirrors.aliyun.com/pypi/simple/"
        $env:PIP_TRUSTED_HOST = "mirrors.aliyun.com"
    }
    if (-not $env:NPM_REGISTRY) {
        $env:NPM_REGISTRY = "https://registry.npmmirror.com"
    }
}

function Get-DockerBuildArgs {
    $args = @()
    $keys = @(
        "PYTHON_BASE_IMAGE",
        "NODE_BASE_IMAGE",
        "NGINX_BASE_IMAGE",
        "PLAYWRIGHT_BASE_IMAGE",
        "PIP_INDEX_URL",
        "PIP_TRUSTED_HOST",
        "NPM_REGISTRY"
    )
    foreach ($key in $keys) {
        $val = (Get-Item -Path "env:$key" -ErrorAction SilentlyContinue).Value
        if ($val) {
            $args += "--build-arg", "${key}=$val"
        }
    }
    return $args
}

function Assert-DockerOk {
    param([string]$Action = "docker command")
    if ($LASTEXITCODE -ne 0) {
        throw "$Action failed (exit code $LASTEXITCODE)"
    }
}

function Get-XlinkImage {
    param([string]$Name)
    return "$($env:IMAGE_PREFIX)/${Name}:$($env:IMAGE_TAG)"
}

function Assert-DockerAvailable {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        throw "docker not found in PATH. Install Docker Desktop and restart the terminal."
    }
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker daemon is not running. Start Docker Desktop first."
    }
}

function Ensure-XlinkNetwork {
    $net = if ($env:XLINK_NETWORK) { $env:XLINK_NETWORK } else { "xlink_net" }
    $exists = docker network ls --format "{{.Name}}" | Select-String -Pattern "^$([regex]::Escape($net))$" -Quiet
    if (-not $exists) {
        docker network create $net | Out-Null
        Write-Host "Created docker network: $net"
    }
    return $net
}

function Stop-XlinkContainerIfExists {
    param([string]$Name)
    $exists = docker ps -a --format "{{.Names}}" | Select-String -Pattern "^$([regex]::Escape($Name))$" -Quiet
    if ($exists) {
        docker rm -f $Name | Out-Null
    }
}

function Get-VolumeArgs {
    param([string]$VolName, [string]$ContainerPath)
    if ($env:DATA_ROOT) {
        $hostPath = Join-Path $env:DATA_ROOT $VolName
        New-Item -ItemType Directory -Force -Path $hostPath | Out-Null
        $mount = "${hostPath}:${ContainerPath}"
        return @("-v", $mount)
    }
    $mount = "${VolName}:${ContainerPath}"
    return @("-v", $mount)
}

# 日志卷默认绑定到仓库内各服务 logs/，便于宿主机直接查看
function Get-LogsVolumeArgs {
    param(
        [ValidateSet("meeting_ai", "influencer_backend", "flybook")]
        [string]$ServiceKey,
        [string]$ContainerPath = "/app/logs"
    )
    $paths = Get-XlinkPaths
    $relativeByService = @{
        meeting_ai           = "meeting_ai\logs"
        influencer_backend   = "Information_Aggregation\backend\logs"
        flybook              = "flybook\logs"
    }
    if ($env:LOGS_ROOT) {
        $hostPath = Join-Path $env:LOGS_ROOT $ServiceKey
    }
    else {
        $hostPath = Join-Path $paths.RootDir $relativeByService[$ServiceKey]
    }
    New-Item -ItemType Directory -Force -Path $hostPath | Out-Null
    return @("-v", "${hostPath}:${ContainerPath}")
}

# 各服务使用自己的 .env；distributed.env 仅放 Docker 网络/基础设施地址
function Get-ServiceEnvFileArgs {
    param([string]$RelativeEnvPath)
    $paths = Get-XlinkPaths
    $envPath = Join-Path $paths.RootDir $RelativeEnvPath
    if (-not (Test-Path $envPath)) {
        throw "Missing service env file: $envPath"
    }
    return @("--env-file", $envPath)
}

function Get-DbInfraOverrides {
    param([string]$DatabaseName)
    $dbHost = if ($env:DB_HOST) { $env:DB_HOST } else { "xlink_mysql" }
    $dbPort = if ($env:DB_PORT) { $env:DB_PORT } else { "3306" }
    $dbUser = if ($env:MYSQL_USER) { $env:MYSQL_USER } else { "app_user" }
    $dbPass = if ($env:MYSQL_PASSWORD) { $env:MYSQL_PASSWORD } else { "app123" }
    return @(
        "-e", "DB_HOST=$dbHost",
        "-e", "DB_PORT=$dbPort",
        "-e", "DB_USER=$dbUser",
        "-e", "DB_PASSWORD=$dbPass",
        "-e", "DB_NAME=$DatabaseName"
    )
}

# 仅当 distributed.env 显式配置时才 -e 覆盖，避免冲掉各服务 .env 中的 CORS 等
function Get-OptionalEnvOverride {
    param([string]$Key)
    $val = (Get-Item -Path "env:$Key" -ErrorAction SilentlyContinue).Value
    if ($null -ne $val -and $val.Trim() -ne "") {
        return @("-e", "${Key}=$val")
    }
    return @()
}
