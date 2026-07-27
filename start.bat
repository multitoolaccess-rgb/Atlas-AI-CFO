@echo off
REM Finance Copilot - Startup Script for Windows
REM This script starts the finance copilot application in development mode

setlocal enabledelayedexpansion

set PROJECT_ROOT=%~dp0
set UI_DIR=%PROJECT_ROOT%ui

echo ==========================================
echo Finance Copilot - Dev Server
echo ==========================================
echo.

REM Check if node_modules exists
if not exist "%UI_DIR%\node_modules" (
    echo 📦 Installing dependencies...
    cd /d "%UI_DIR%"
    call npm install
    echo.
)

REM Clean cache for fresh start
echo 🧹 Cleaning cache...
cd /d "%UI_DIR%"
rmdir /s /q .next 2>nul
rmdir /s /q node_modules\.cache 2>nul

echo.
echo 🚀 Starting dev server...
echo    - App will be available at: http://localhost:3000
echo    - Press Ctrl+C to stop
echo.

call npm run dev

pause
