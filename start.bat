@echo off
chcp 65001 >nul
title Tech-Bid-Engine 启动器
cd /d "%~dp0"

echo ========================================
echo   Tech-Bid-Engine 技术方案生成系统 V5.0
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.11+
    pause
    exit /b 1
)

if not exist "venv\Scripts\python.exe" (
    echo [1/5] 正在创建虚拟环境...
    python -m venv venv
)

echo [2/5] 检查 Python 依赖...
venv\Scripts\pip install -q -r requirements.txt
if errorlevel 1 (
    venv\Scripts\pip install -q fastapi uvicorn sqlalchemy python-multipart python-dotenv openai pymupdf pdfplumber python-docx
)

if not exist ".env" (
    echo [3/5] 创建配置文件 .env ...
    copy /Y .env.example .env >nul
) else (
    echo [3/5] 配置文件 .env 已存在
)

echo [4/5] 下载前端依赖并编译界面...
venv\Scripts\python download_vendor.py
call npm install >nul 2>&1
call npm run build:frontend
if errorlevel 1 (
    echo [错误] 前端编译失败，请确认已安装 Node.js
    pause
    exit /b 1
)

echo [4.5/5] 检查 Graphviz（流程图/组织架构图渲染依赖）...
where dot >nul 2>&1
if errorlevel 1 (
    if exist "C:\Program Files\Graphviz\bin\dot.exe" (
        echo   已检测到 Graphviz（安装于 Program Files，但未加入 PATH）
    ) else (
        echo.
        echo   [警告] 未检测到 Graphviz，工艺流程图/组织架构图将退化为警示图片，
        echo          会直接出现在导出的 Word 文档中！
        echo          建议安装： winget install Graphviz.Graphviz
        echo          安装完成后需重新运行本脚本。
        echo.
    )
) else (
    echo   Graphviz 已就绪
)

echo [5/5] 初始化数据库...
venv\Scripts\python -c "from db.database import init_db; init_db()"
if errorlevel 1 (
    echo [错误] 数据库初始化失败
    pause
    exit /b 1
)

for /f "tokens=2 delims==" %%a in ('findstr /B "API_PORT" .env 2^>nul') do set API_PORT=%%a
if not defined API_PORT set API_PORT=3333

echo 检查端口 %API_PORT% 占用...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%API_PORT%" ^| findstr LISTENING') do (
    echo 结束占用端口的旧进程 PID=%%a
    taskkill /F /PID %%a >nul 2>&1
)

for /f "tokens=2" %%a in ('wmic process where "CommandLine like '%%biao%%uvicorn%%'" get ProcessId /format:list 2^>nul ^| findstr "="') do (
    echo 结束残留 uvicorn 进程 PID=%%a
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo 服务启动中...
echo   访问地址: http://localhost:%API_PORT%
echo   按 Ctrl+C 可停止服务
echo.

start "" "http://localhost:%API_PORT%"
venv\Scripts\uvicorn main:app --host 0.0.0.0 --port %API_PORT% --reload

pause
