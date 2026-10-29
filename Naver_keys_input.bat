@echo off
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] venv folder not found. Keep this file inside the project folder.
    pause
    exit /b 1
)
echo ============================================
echo   Naver SearchAd keys input (values are hidden)
echo   Paste each value and press Enter.
echo ============================================
echo.
venv\Scripts\python.exe -X utf8 scripts\set_env_secrets.py NAVER_AD_API_KEY NAVER_AD_SECRET_KEY NAVER_AD_CUSTOMER_ID
echo.
pause
