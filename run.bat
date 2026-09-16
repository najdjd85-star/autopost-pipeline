@echo off
chcp 65001 >nul
title Media Pipeline
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] venv not found. Make sure this file stays inside the project folder.
    pause
    exit /b 1
)

:menu
cls
echo ============================================
echo   3-Site Passive Media Pipeline
echo ============================================
echo   1. Run Site A  (government subsidy)
echo   2. Run Site B  (telecom/rental)
echo   3. Run Site C  (tax refund)
echo   4. Run ALL sites
echo   5. Search Console rank-defense check
echo   6. Send weekly newsletter now
echo   7. Start daemon mode (scheduler+bot+server)
echo   8. Open .env settings file
echo   0. Exit
echo ============================================
echo.
set /p choice="Enter a number and press Enter: "

if "%choice%"=="1" (venv\Scripts\python.exe main.py run-now site_a & goto end)
if "%choice%"=="2" (venv\Scripts\python.exe main.py run-now site_b & goto end)
if "%choice%"=="3" (venv\Scripts\python.exe main.py run-now site_c & goto end)
if "%choice%"=="4" (venv\Scripts\python.exe main.py run-now all & goto end)
if "%choice%"=="5" (venv\Scripts\python.exe main.py refresh-check & goto end)
if "%choice%"=="6" (venv\Scripts\python.exe main.py send-newsletter & goto end)
if "%choice%"=="7" (venv\Scripts\python.exe main.py daemon & goto end)
if "%choice%"=="8" (notepad .env & goto menu)
if "%choice%"=="0" exit

echo.
echo Invalid input. Please enter a number from 0 to 8.
pause
goto menu

:end
echo.
echo ============================================
echo   Finished. (Ctrl+C to stop is also normal)
echo ============================================
pause
goto menu
