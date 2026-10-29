@echo off
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] venv folder not found. Keep this file inside the project folder.
    pause
    exit /b 1
)
echo ============================================
echo   Gemini API key input (keys are hidden)
echo ============================================
echo.
venv\Scripts\python.exe -X utf8 scripts\set_gemini_keys.py %*
echo.
pause
