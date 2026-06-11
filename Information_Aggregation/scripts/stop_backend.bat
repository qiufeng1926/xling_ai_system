@echo off
chcp 65001 >nul
echo ========================================
echo   停止所有后端进程（清理 8000 端口）
echo ========================================

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo 停止 PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

for /f "tokens=2" %%a in ('wmic process where "commandline like '%%app.main:app%%'" get processid /format:list 2^>nul ^| findstr "="') do (
    echo 停止 uvicorn PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

timeout /t 2 /nobreak >nul
echo 完成。
pause
