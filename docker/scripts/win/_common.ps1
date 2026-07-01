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
            Write-Host "Created env from template: $EnvFile"
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
