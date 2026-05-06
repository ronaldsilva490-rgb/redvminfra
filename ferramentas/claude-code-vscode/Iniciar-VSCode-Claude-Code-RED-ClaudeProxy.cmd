@echo off
setlocal EnableExtensions
title VS Code + Claude Code RED Claude Proxy

set "CONFIG_SCRIPT=%~dp0Configurar-Claude-Code-RED-ClaudeProxy.ps1"
if not exist "%CONFIG_SCRIPT%" set "CONFIG_SCRIPT=C:\Projetos\redvm\ferramentas\claude-code-vscode\Configurar-Claude-Code-RED-ClaudeProxy.ps1"

if exist "%CONFIG_SCRIPT%" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CONFIG_SCRIPT%"
)

set "ANTHROPIC_BASE_URL=https://redsystems.ddns.net/redclaudeproxy"
set "ANTHROPIC_API_KEY=red"
set "ANTHROPIC_AUTH_TOKEN=red"
set "ANTHROPIC_MODEL=claude-red-devstral-medium"
set "ANTHROPIC_DEFAULT_SONNET_MODEL=claude-red-devstral-medium"
set "ANTHROPIC_DEFAULT_OPUS_MODEL=claude-red-nim-glm51"
set "ANTHROPIC_DEFAULT_HAIKU_MODEL=claude-red-mistral-small"
set "ANTHROPIC_CUSTOM_MODEL_OPTION=claude-red-nim-glm51"
set "ANTHROPIC_CUSTOM_MODEL_OPTION_NAME=RED NIM GLM 5.1"
set "ANTHROPIC_CUSTOM_MODEL_OPTION_DESCRIPTION=RED Claude Proxy"
set "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1"
set "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1"
set "CLAUDE_CODE_MAX_RETRIES=2"
set "API_TIMEOUT_MS=600000"

set "CODE_EXE=%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"
if not exist "%CODE_EXE%" set "CODE_EXE=code"

if "%~1"=="" (
  start "" "%CODE_EXE%" "C:\Projetos"
) else (
  start "" "%CODE_EXE%" %*
)

exit /b 0
