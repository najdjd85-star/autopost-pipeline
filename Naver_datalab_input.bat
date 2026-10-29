@echo off
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] venv folder not found. Keep this file inside the project folder.
    pause
    exit /b 1
)
echo ============================================
echo   Naver DataLab app keys (new app from developers.naver.com)
echo   Paste Client ID, then Client Secret (hidden).
echo   Saved as NAVER_DATALAB_ID / NAVER_DATALAB_SECRET
echo   (your existing NAVER_CLIENT_* keys are NOT touched)
echo ============================================
echo.
venv\Scripts\python.exe -X utf8 scripts\set_env_secrets.py NAVER_DATALAB_ID NAVER_DATALAB_SECRET
echo.
pause
