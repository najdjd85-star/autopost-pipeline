@echo off
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] venv folder not found. Keep this file inside the project folder.
    pause
    exit /b 1
)
echo ============================================
echo   Naver DataLab app keys input (values are hidden)
echo   Paste Client ID, then Client Secret.
echo ============================================
echo.
venv\Scripts\python.exe -X utf8 scripts\set_env_secrets.py NAVER_CLIENT_ID NAVER_CLIENT_SECRET
echo.
pause
