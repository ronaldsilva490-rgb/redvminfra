@echo off
setlocal EnableExtensions
title Ativar VMP para Claude Desktop

where powershell.exe >nul 2>nul
if errorlevel 1 (
  echo PowerShell nao foi encontrado neste Windows.
  pause
  exit /b 1
)

net session >nul 2>nul
if errorlevel 1 (
  echo [RED] Solicitando permissao de administrador...
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b 0
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "function State($name){ try{ $f=Get-CimInstance Win32_OptionalFeature -Filter \"Name='$name'\"; if($null -eq $f){return 'nao encontrado'}; switch([int]$f.InstallState){1{'ativo'}2{'desativado'}3{'ausente'}default{'estado '+$f.InstallState}} } catch { 'nao consultado' } }" ^
  "Write-Host '===============================================' -ForegroundColor DarkRed;" ^
  "Write-Host '  RED - Ativar VMP para Claude Desktop' -ForegroundColor Red;" ^
  "Write-Host '===============================================' -ForegroundColor DarkRed;" ^
  "Write-Host '';" ^
  "Write-Host ('VirtualMachinePlatform antes: ' + (State 'VirtualMachinePlatform')) -ForegroundColor Cyan;" ^
  "Write-Host ('HypervisorPlatform antes: ' + (State 'HypervisorPlatform')) -ForegroundColor Cyan;" ^
  "Write-Host '';" ^
  "Write-Host '[RED] Ativando VirtualMachinePlatform...' -ForegroundColor Cyan;" ^
  "dism.exe /Online /Enable-Feature /FeatureName:VirtualMachinePlatform /All /NoRestart;" ^
  "Write-Host '[RED] Ativando HypervisorPlatform...' -ForegroundColor Cyan;" ^
  "dism.exe /Online /Enable-Feature /FeatureName:HypervisorPlatform /All /NoRestart;" ^
  "Write-Host '[RED] Garantindo hypervisor no boot...' -ForegroundColor Cyan;" ^
  "bcdedit.exe /set hypervisorlaunchtype auto;" ^
  "Write-Host '';" ^
  "Write-Host ('VirtualMachinePlatform depois: ' + (State 'VirtualMachinePlatform')) -ForegroundColor Green;" ^
  "Write-Host ('HypervisorPlatform depois: ' + (State 'HypervisorPlatform')) -ForegroundColor Green;" ^
  "Write-Host '';" ^
  "Write-Host 'Pronto. Reinicie o Windows para o Claude Desktop parar de pedir VMP.' -ForegroundColor Yellow;"

echo.
pause
