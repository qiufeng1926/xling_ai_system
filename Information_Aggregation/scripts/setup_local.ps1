param(
    [string]$RootPassword = $env:MYSQL_ROOT_PASSWORD
)

$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::UTF8
[Console]::InputEncoding = [Text.UTF8Encoding]::UTF8
chcp 65001 | Out-Null

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$sqlFile = Join-Path $scriptDir "setup_local.sql"

if (-not $RootPassword) {
    $RootPassword = Read-Host "MySQL root password"
}

$cnfFile = Join-Path $env:TEMP "mysql_setup_$([guid]::NewGuid().ToString('N')).cnf"
@"
[client]
user=root
password=$RootPassword
host=localhost
"@ | Set-Content -Path $cnfFile -Encoding ASCII

try {
    Write-Host "Initializing database influencer_db ..."

    $mysqlArgs = @(
        "--defaults-extra-file=$cnfFile",
        "--default-character-set=utf8mb4"
    )

    Get-Content $sqlFile -Encoding UTF8 -Raw | & mysql @mysqlArgs
    if ($LASTEXITCODE -ne 0) {
        throw "mysql exited with code $LASTEXITCODE"
    }

    Write-Host "[SUCCESS] Database initialized!"
    Write-Host "  User: app_user / app123 @ localhost:3306 / influencer_db"
}
catch {
    Write-Host ""
    Write-Host "[ERROR] Setup failed. Check root password and MySQL service."
    Write-Host ""
    Write-Host "Alternative - use Python script:"
    Write-Host "  python scripts/setup_db.py"
    exit 1
}
finally {
    if (Test-Path $cnfFile) {
        Remove-Item $cnfFile -Force
    }
}
