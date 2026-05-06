@echo off
setlocal EnableExtensions
title Claude RED - sem VMP

set "CLAUDE_RED_EXE=C:\Projetos\ClaudeREDDesktop\app\Claude.exe"

if not exist "%CLAUDE_RED_EXE%" (
  echo Claude RED portatil nao encontrado:
  echo %CLAUDE_RED_EXE%
  echo.
  echo Rode a preparacao do Claude RED antes de usar este launcher.
  pause
  exit /b 1
)

taskkill /IM Claude.exe /F >nul 2>nul
timeout /t 1 /nobreak >nul

set "CHAT_FIX=%~dp0Preparar-Claude-RED-Chat.ps1"
if not exist "%CHAT_FIX%" set "CHAT_FIX=C:\Projetos\redvm\ferramentas\claude-desktop\Preparar-Claude-RED-Chat.ps1"

if exist "%CHAT_FIX%" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CHAT_FIX%"
)

start "" "%CLAUDE_RED_EXE%" --no-sandbox
exit /b 0
