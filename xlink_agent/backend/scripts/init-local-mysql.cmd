@echo off
REM 本机 MySQL（无 Docker）为 xlink_agent 建库并授权 app_user
REM 用法: 双击或在 cmd 中运行；可用环境变量覆盖账号
REM   set MYSQL_ROOT_PASSWORD=root
REM   set MYSQL_USER=app_user
REM   set MYSQL_PASSWORD=app123

setlocal
set ROOT_PASS=%MYSQL_ROOT_PASSWORD%
if "%ROOT_PASS%"=="" set ROOT_PASS=root
set APP_USER=%MYSQL_USER%
if "%APP_USER%"=="" set APP_USER=app_user
set APP_PASS=%MYSQL_PASSWORD%
if "%APP_PASS%"=="" set APP_PASS=app123

set MYSQL_EXE=
if exist "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" set MYSQL_EXE=C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe
if exist "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe" set MYSQL_EXE=C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe
if "%MYSQL_EXE%"=="" (
  where mysql >nul 2>&1 && set MYSQL_EXE=mysql
)
if "%MYSQL_EXE%"=="" (
  echo ERROR: 找不到 mysql.exe
  exit /b 1
)

"%MYSQL_EXE%" -uroot -p%ROOT_PASS% -e "CREATE DATABASE IF NOT EXISTS xlink_agent CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; CREATE USER IF NOT EXISTS '%APP_USER%'@'localhost' IDENTIFIED BY '%APP_PASS%'; CREATE USER IF NOT EXISTS '%APP_USER%'@'%%' IDENTIFIED BY '%APP_PASS%'; ALTER USER '%APP_USER%'@'localhost' IDENTIFIED BY '%APP_PASS%'; ALTER USER '%APP_USER%'@'%%' IDENTIFIED BY '%APP_PASS%'; GRANT ALL PRIVILEGES ON xlink_agent.* TO '%APP_USER%'@'localhost'; GRANT ALL PRIVILEGES ON xlink_agent.* TO '%APP_USER%'@'%%'; FLUSH PRIVILEGES;"
if errorlevel 1 (
  echo.
  echo ERROR: root 登录失败。请设置 MYSQL_ROOT_PASSWORD 后重试。
  exit /b 1
)
echo OK: database xlink_agent granted to %APP_USER%
endlocal
