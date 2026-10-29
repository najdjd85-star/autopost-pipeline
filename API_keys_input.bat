@echo off
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] venv folder not found. Keep this file inside the project folder.
    pause
    exit /b 1
)
echo ============================================
echo   API key input - any name, hidden value
echo   Type the NAME (e.g. NAVER_DATALAB_ID), Enter,
echo   then paste the VALUE (it will not be shown).
echo   Type  list  to see existing names.
echo ============================================
echo.
venv\Scripts\python.exe -X utf8 scripts\set_env_secrets.py
echo.
pause
