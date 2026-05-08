@echo off
setlocal
set "SEB_PORTABLE=1"
set "BASE_DIR=%~dp0"
set "CONFIG=%~1"
if "%CONFIG%"=="" set "CONFIG=%BASE_DIR%config.seb"
if not exist "%CONFIG%" (
  echo Configuracao nao encontrada: %CONFIG%
  pause
  exit /b 1
)
start "RED SEB Portable" "%BASE_DIR%SafeExamBrowser.exe" "%CONFIG%"
