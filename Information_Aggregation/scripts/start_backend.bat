@echo off
chcp 65001 >nul
cd /d %~dp0..\backend

set PYTHON=D:\AI\miniconda\envs\information\python.exe
if not exist "%PYTHON%" set PYTHON=python

echo ========================================
echo   停止旧的后端进程（含僵尸 worker）
echo ========================================

REM 杀掉占用 8000 端口的进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo Killing PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

REM 杀掉 orphaned uvicorn worker（父进程已死但 worker 仍存活）
for /f "tokens=2" %%a in ('wmic process where "commandline like '%%app.main:app%%'" get processid /format:list ^| findstr "="') do (
    echo Killing uvicorn worker PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

timeout /t 2 /nobreak >nul

echo.
echo Starting backend with: %PYTHON%
echo ========================================
"%PYTHON%" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
