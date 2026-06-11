Set-Location $PSScriptRoot\..\backend

$python = "D:\AI\miniconda\envs\information\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

Write-Host "Stopping old backend processes..."

Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

Get-CimInstance Win32_Process -Filter "name='python.exe'" |
    Where-Object { $_.CommandLine -like "*app.main:app*" } |
    ForEach-Object {
        Write-Host "Killing PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Start-Sleep -Seconds 2

Write-Host "Starting backend with: $python"
& $python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
