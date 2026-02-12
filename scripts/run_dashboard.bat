@echo off
setlocal

REM Set project root directory (parent of current script directory)
cd /d "%~dp0.."
set "PROJECT_ROOT=%cd%"

REM Activate virtual environment if it exists
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

REM Add current directory to PYTHONPATH
set PYTHONPATH=%PROJECT_ROOT%;%PYTHONPATH%

REM Start browser (start command is non-blocking)
echo Opening browser...
start "" "http://localhost:5007"

REM Start Flask server
echo Starting Strategy Dashboard on http://localhost:5007...
python src/web/app.py

REM Pause if error occurs
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Application exited with error code %ERRORLEVEL%
    pause
) else (
    echo.
    echo Application stopped.
    pause
)

endlocal
