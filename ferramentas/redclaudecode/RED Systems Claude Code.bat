@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "REPO_ROOT=%SCRIPT_DIR%..\.."

pushd "%REPO_ROOT%" >nul

where pythonw >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PYTHON_CMD=pythonw"
) else (
    set "PYTHON_CMD=python"
)

%PYTHON_CMD% -m ferramentas.redclaudecode
set "EXIT_CODE=%ERRORLEVEL%"

popd >nul

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Falha ao abrir o launcher RED Claude Code.
    echo.
    pause
)

endlocal & exit /b %EXIT_CODE%
