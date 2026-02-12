@echo off
title FundVision - Fund Analysis System

echo.
echo ============================================================
echo          FundVision - Fund Analysis System
echo                   v6.4 Compare-Edition
echo ============================================================
echo.

REM Check Python
echo [1/4] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo     [ERROR] Python not found!
    echo     Please install Python 3.8+ from: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo     [OK] Python %PYTHON_VER%
echo.

REM Check port 5000
echo [2/4] Checking port 5000...
netstat -ano | findstr ":5000" | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo     [WARNING] Port 5000 is in use
    echo     Trying to close the process...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING"') do (
        taskkill /f /pid %%a >nul 2>&1
    )
    timeout /t 2 /nobreak >nul
)
echo     [OK] Port available
echo.

REM Check and install dependencies
echo [3/4] Checking dependencies...
if exist "requirements.txt" (
    python -c "import flask" >nul 2>&1
    if %errorlevel% neq 0 (
        echo     Installing dependencies...
        python -m pip install -r requirements.txt -q
        if %errorlevel% neq 0 (
            echo     [ERROR] Failed to install dependencies!
            echo     Please run manually: pip install -r requirements.txt
            pause
            exit /b 1
        )
        echo     [OK] Dependencies installed
    ) else (
        echo     [OK] Dependencies already installed
    )
) else (
    echo     [WARNING] requirements.txt not found
)
echo.

REM Check .env file
echo [4/4] Checking configuration...
if exist ".env" (
    echo     [OK] Config file exists
) else (
    if exist ".env.example" (
        echo     [INFO] .env not found, copying from .env.example...
        copy .env.example .env >nul 2>&1
        echo     [OK] Created .env file, please edit AI_API_KEY
    ) else (
        echo     [WARNING] Config template not found
    )
)
echo.

REM Start server
echo ============================================================
echo Starting server...
echo ============================================================
echo.

start /min cmd /c "python app.py"

REM Wait for server
echo Waiting for server to start...
set COUNT=0

:wait_loop
timeout /t 1 /nobreak >nul
set /a COUNT+=1
curl -s http://localhost:5000/api/health >nul 2>&1
if %errorlevel% equ 0 goto server_ready
if %COUNT% geq 15 goto server_timeout
goto wait_loop

:server_ready
echo.
echo ============================================================
echo                 Server started successfully!
echo ============================================================
echo   Backend API:  http://localhost:5000
echo   Frontend:     Opening automatically...
echo ============================================================
echo   API Endpoints:
echo   - GET  /api/health              Health check
echo   - GET  /api/search_fund         Fund search
echo   - GET  /api/fund_info/^<code^>    Fund info
echo   - POST /api/parse_funds         AI parse
echo   - POST /api/fund_analysis       Full analysis
echo   - POST /api/estimate            Estimate only
echo   - POST /api/drawdown            Drawdown only
echo   - GET  /api/get_indices         Real-time indices
echo   - GET  /api/get_fund_detail     Fund holdings
echo   - GET  /api/get_nav_history     Nav history
echo   - GET  /api/get_nav_history_batch Batch nav
echo ============================================================
echo.

REM Open frontend
if exist "index.html" (
    start index.html
    echo [INFO] Frontend opened
) else (
    echo [WARNING] index.html not found
)
echo.
echo Press any key to stop the server...
pause >nul

REM Stop server
echo.
echo Stopping server...
taskkill /f /im python.exe >nul 2>&1
echo Server stopped.
timeout /t 2 /nobreak >nul
exit /b 0

:server_timeout
echo.
echo [ERROR] Server startup timeout!
echo Please check the logs or run manually: python app.py
pause
exit /b 1
