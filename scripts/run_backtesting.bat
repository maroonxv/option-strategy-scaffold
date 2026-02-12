@echo off
cd /d "%~dp0.."
set PYTHONPATH=%cd%
call .venv\Scripts\activate.bat
set LOGDIR=%cd%\data\backtesting
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
set LOGFILE=%LOGDIR%\backtesting_%TS%.log
powershell -NoProfile -ExecutionPolicy Bypass -Command "python -m src.backtesting.cli 2>&1 | Tee-Object -FilePath \"%LOGFILE%\""
echo.
echo Log saved to: %LOGFILE%
pause
