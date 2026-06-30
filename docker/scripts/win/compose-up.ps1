# Compose 全栈启动
# 用法: .\docker\scripts\win\compose-up.ps1

. "$PSScriptRoot\_common.ps1"
$paths = Get-XlinkPaths
$composeEnv = Join-Path $paths.DockerDir ".env"
if (-not (Test-Path $composeEnv)) {
    Copy-Item (Join-Path $paths.DockerDir ".env.example") $composeEnv
    Write-Error "已生成 $composeEnv ，请修改后重新运行"
}
Set-Location $paths.RootDir
docker compose --env-file $composeEnv up -d --build @args
