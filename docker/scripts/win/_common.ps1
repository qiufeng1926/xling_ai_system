# xlink Docker 启动脚本（Windows PowerShell）
# 用法见各脚本顶部注释；环境文件默认 docker\env\distributed.env

$ErrorActionPreference = "Stop"

function Get-XlinkPaths {
    $ScriptDir = Split-Path -Parent $MyInvocation.ScriptName
    if (-not $ScriptDir) { $ScriptDir = $PSScriptRoot }
    $DockerDir = Resolve-Path (Join-Path $ScriptDir "..")
    $RootDir = Resolve-Path (Join-Path $DockerDir "..")
    return @{ ScriptDir = $ScriptDir; DockerDir = $DockerDir; RootDir = $RootDir }
}

function Import-XlinkEnv {
    param([string]$EnvFile)
    $paths = Get-XlinkPaths
    if (-not $EnvFile) {
        $EnvFile = Join-Path $paths.DockerDir "env\distributed.env"
    }
    if (-not (Test-Path $EnvFile)) {
        $example = Join-Path $paths.DockerDir "env\distributed.env.example"
        Write-Error "未找到 $EnvFile ，请先复制: copy $example $EnvFile"
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

function Ensure-XlinkNetwork {
    $net = if ($env:XLINK_NETWORK) { $env:XLINK_NETWORK } else { "xlink_net" }
    $exists = docker network ls --format "{{.Name}}" | Select-String -Pattern "^$([regex]::Escape($net))$" -Quiet
    if (-not $exists) {
        docker network create $net | Out-Null
        Write-Host "已创建 Docker 网络: $net"
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
        return @("-v", "${hostPath}:${ContainerPath}")
    }
    return @("-v", "${VolName}:${ContainerPath}")
}
