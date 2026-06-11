@echo off
chcp 65001 >nul
echo ========================================
echo   停止所有前后端进程
echo ========================================

echo [1/5] 停止 8000 端口（后端）...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo   taskkill /F /T /PID %%a
    taskkill /F /T /PID %%a >nul 2>&1
)

echo [2/5] 停止 5173、5174 端口（前端）...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173" ^| findstr "LISTENING"') do taskkill /F /T /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5174" ^| findstr "LISTENING"') do taskkill /F /T /PID %%a >nul 2>&1

echo [3/5] 停止本项目 uvicorn 进程...
for /f "tokens=2" %%a in ('wmic process where "commandline like '%%Information_Aggregation%%app.main%%'" get processid /format:list 2^>nul ^| findstr "="') do (
    taskkill /F /T /PID %%a >nul 2>&1
)

echo [4/5] 停止本项目 vite/node 进程...
for /f "tokens=2" %%a in ('wmic process where "commandline like '%%Information_Aggregation%%frontend%%'" get processid /format:list 2^>nul ^| findstr "="') do (
    taskkill /F /T /PID %%a >nul 2>&1
)

echo [5/5] 清理 uvicorn 孤儿 worker（父进程已退出但子进程仍占 8000）...
for /f "tokens=2" %%a in ('wmic process where "name='python.exe' and commandline like '%%spawn_main%%' and commandline like '%%information%%'" get processid /format:list 2^>nul ^| findstr "="') do (
    echo   taskkill /F /T /PID %%a
    taskkill /F /T /PID %%a >nul 2>&1
)

for /f "tokens=2" %%a in ('wmic process where "commandline like '%%Information_Aggregation%%'" get processid /format:list 2^>nul ^| findstr "="') do (
    taskkill /F /T /PID %%a >nul 2>&1
)

timeout /t 2 /nobreak >nul

echo.
echo 检查剩余端口:
netstat -ano | findstr "LISTENING" | findstr ":8000 :5173 :5174"
if errorlevel 1 (
    echo   8000 / 5173 / 5174 均已释放
) else (
    echo   仍有进程占用，请手动关闭上述 PID
)
echo.
echo 完成。可运行 start_dev.bat 重新启动。
pause
