@echo off
setlocal
set "SCRIPT=%~dp0Claude CLI - RED InferProxy.ps1"

where wt.exe >nul 2>nul
if %errorlevel%==0 (
  start "" wt.exe -w new new-tab --title "Claude Code - RED InferProxy" powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
  exit /b 0
)

powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
pause
