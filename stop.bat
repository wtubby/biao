@echo off
chcp 65001 >nul
title Tech-Bid-Engine 停止服务
cd /d "%~dp0"

echo 正在停止本项目所有 uvicorn 进程...

for /f "tokens=2 delims==" %%a in ('findstr /B "API_PORT" .env 2^>nul') do set API_PORT=%%a
if not defined API_PORT set API_PORT=3333

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%API_PORT%" ^| findstr LISTENING') do (
    echo 结束端口 %API_PORT% 进程 PID=%%a
    taskkill /F /PID %%a >nul 2>&1
)

for /f "tokens=2" %%a in ('wmic process where "CommandLine like '%%biao%%uvicorn%%'" get ProcessId /format:list 2^>nul ^| findstr "="') do (
    echo 结束 uvicorn 进程 PID=%%a
    taskkill /F /PID %%a >nul 2>&1
)

echo 完成。
pause
