@echo off
chcp 65001 >nul
REM OTC Fund NAV Estimator - 启动脚本

echo ==========================================
echo   OTC Fund NAV Estimator
echo ==========================================
echo.

REM 获取脚本所在目录
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM 检查 Python 环境
echo [1/3] 检查 Python 环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python！
    echo.
    echo 请检查以下事项：
    echo   1. Python 3.8+ 是否已安装
    echo   2. Python 是否已添加到系统 PATH
    echo   3. 或修改此脚本使用 Python 的完整路径
    echo.
    echo 安装 Python: https://python.org/downloads
    pause
    exit /b 1
)
python --version
echo.

REM 检查依赖
echo [2/3] 检查依赖...
if not exist "requirements.txt" (
    echo [警告] 未找到 requirements.txt
    goto :skip_deps
)

python -c "import flask" >nul 2>&1
if %errorlevel% neq 0 (
    echo 正在安装依赖...
    python -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [错误] 依赖安装失败
        pause
        exit /b 1
    )
)
echo 依赖检查完成
echo.

:skip_deps

REM 启动应用
echo [3/3] 启动服务...
echo   访问地址: http://localhost:5000
echo   按 Ctrl+C 停止服务
echo.
echo ==========================================
echo.

python app.py

REM 如果启动失败
if %errorlevel% neq 0 (
    echo.
    echo [错误] 应用启动失败！
    echo.
    echo 常见问题：
    echo   - 端口 5000 被占用：修改 app.py 中的端口
    echo   - 缺少环境变量：复制 .env.example 为 .env 并配置
    echo   - API 密钥未设置：设置 AI_API_KEY 环境变量
    pause
)
