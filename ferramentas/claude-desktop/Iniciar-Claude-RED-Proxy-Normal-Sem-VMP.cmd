@echo off
setlocal EnableExtensions
title Claude RED - Proxy Normal Completo

set "CLAUDE_RED_EXE=C:\Projetos\ClaudeREDDesktop\app\Claude.exe"
if not exist "%CLAUDE_RED_EXE%" set "CLAUDE_RED_EXE=%LOCALAPPDATA%\Programs\Claude\Claude.exe"

if not exist "%CLAUDE_RED_EXE%" (
  echo Claude Desktop nao encontrado.
  echo Procurei em:
  echo   C:\Projetos\ClaudeREDDesktop\app\Claude.exe
  echo   %LOCALAPPDATA%\Programs\Claude\Claude.exe
  echo.
  pause
  exit /b 1
)

set "CHAT_FIX=%~dp0Preparar-Claude-RED-Proxy-Normal.ps1"
if not exist "%CHAT_FIX%" set "CHAT_FIX=C:\Projetos\redvm\ferramentas\claude-desktop\Preparar-Claude-RED-Proxy-Normal.ps1"

if not exist "%CHAT_FIX%" (
  echo Script de preparo nao encontrado:
  echo %CHAT_FIX%
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CHAT_FIX%"
if errorlevel 1 (
  echo.
  echo Falha ao configurar o Claude para o proxy normal completo.
  pause
  exit /b 1
)

start "" "%CLAUDE_RED_EXE%" --no-sandbox
exit /b 0
