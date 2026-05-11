@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Preparar-Claude-RED-InferProxy.ps1"
pause
