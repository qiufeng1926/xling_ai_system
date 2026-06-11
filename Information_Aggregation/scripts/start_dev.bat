@echo off
chcp 65001 >nul
echo ========================================
echo   达人聚合系统 - 一键启动开发环境
echo ========================================

set PYTHON=D:\AI\miniconda\envs\information\python.exe
if not exist "%PYTHON%" set PYTHON=python

REM 1. 清理旧进程
echo [1/3] 清理旧进程（8000 / 5173 / 5174）...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do taskkill /F /T /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173" ^| findstr "LISTENING"') do taskkill /F /T /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5174" ^| findstr "LISTENING"') do taskkill /F /T /PID %%a >nul 2>&1
for /f "tokens=2" %%a in ('wmic process where "commandline like '%%Information_Aggregation%%app.main%%'" get processid /format:list 2^>nul ^| findstr "="') do taskkill /F /T /PID %%a >nul 2>&1
timeout /t 2 /nobreak >nul

REM 2. 启动后端（新窗口）
echo [2/3] 启动后端 http://0.0.0.0:8000
start "后端-请勿关闭此窗口" cmd /k "cd /d %~dp0..\backend && echo 后端 Python: %PYTHON% && "%PYTHON%" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

timeout /t 3 /nobreak >nul

REM 3. 启动前端（新窗口）
echo [3/3] 启动前端 http://127.0.0.1:5173
start "前端-请勿关闭此窗口" cmd /k "cd /d %~dp0..\frontend && npm run dev"

echo.
echo 启动完成！请保持「后端」和「前端」两个窗口运行。
echo   前端: http://127.0.0.1:5173  （局域网可用本机 IP:5173）
echo   后端: http://127.0.0.1:8000/docs  （局域网可用本机 IP:8000）
echo.
echo 后端收到请求时会打印: GET /api/v1/... -^> 200
pause
