@echo off

REM Simple start script for FundVision

echo FundVision - Start Script
echo ================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python not found!
    echo Please install Python 3.8+ first.
    echo.
    pause
    exit /b 1
)

echo Python found: OK
echo.

REM Check requirements
if exist "requirements.txt" (
    python -c "import flask" >nul 2>&1
    if %errorlevel% neq 0 (
        echo Installing dependencies...
        python -m pip install -r requirements.txt
        if %errorlevel% neq 0 (
            echo Error: Failed to install dependencies!
            pause
            exit /b 1
        )
    )
    echo Dependencies: OK
) else (
    echo Warning: requirements.txt not found
)
echo.

REM Start server
start /MIN cmd /c "python app.py"

REM Wait for server to start
echo Starting server...
timeout /t 5 /nobreak >nul

REM Open frontend
echo Opening frontend...
start index.html

echo.
echo Server started successfully!
echo Access: http://localhost:5000
echo.
echo Press any key to stop server...
pause >nul

REM Stop server
taskkill /f /im python.exe /fi "WINDOWTITLE eq cmd.exe"

echo Server stopped.
pause
