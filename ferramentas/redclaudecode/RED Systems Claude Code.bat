@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "LAUNCHER_PS1=%SCRIPT_DIR%RED Systems Claude Code.ps1"

if not exist "%LAUNCHER_PS1%" (
    echo.
    echo ERRO: launcher PowerShell nao encontrado.
    echo Caminho esperado: "%LAUNCHER_PS1%"
    echo.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%LAUNCHER_PS1%"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Launcher encerrado com codigo %EXIT_CODE%.
    echo.
    pause
)

endlocal & exit /b %EXIT_CODE%
