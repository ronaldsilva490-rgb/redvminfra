@echo off
setlocal EnableExtensions
chcp 65001 >nul
title RED Systems - Claude Code

set "RED_BAT=%~f0"
set "RED_WORKSPACE=%~dp0"
if "%RED_PROXY_BASE%"=="" set "RED_PROXY_BASE=http://redsystems.ddns.net/proxy"
if "%RED_PROXY_KEY%"=="" set "RED_PROXY_KEY=red"

cd /d "%RED_WORKSPACE%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $raw=[IO.File]::ReadAllText($env:RED_BAT,[Text.Encoding]::UTF8); $marker='### RED_POWERSHELL ###'; $idx=$raw.LastIndexOf($marker); if($idx -lt 0){ throw 'Bloco PowerShell nao encontrado.' }; $ps=$raw.Substring($idx + $marker.Length); Invoke-Expression $ps"
set "RED_EXIT=%ERRORLEVEL%"

if not "%RED_EXIT%"=="0" (
    echo.
    echo RED Claude Code terminou com erro: %RED_EXIT%
    echo.
    pause
)

endlocal & exit /b %RED_EXIT%

### RED_POWERSHELL ###
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$Host.UI.RawUI.WindowTitle = "RED Systems | Claude Code"

$baseUrl = ($env:RED_PROXY_BASE).TrimEnd("/")
$apiKey = $env:RED_PROXY_KEY
$workspace = (Resolve-Path -LiteralPath $env:RED_WORKSPACE).Path
$modelEndpoint = "${baseUrl}/v1/models"

function Write-RedHeader {
    param([string]$Subtitle = "")
    Clear-Host
    Write-Host ""
    Write-Host "██████╗ ███████╗██████╗ " -ForegroundColor Red
    Write-Host "██╔══██╗██╔════╝██╔══██╗" -ForegroundColor Red
    Write-Host "██████╔╝█████╗  ██║  ██║" -ForegroundColor Red
    Write-Host "██╔══██╗██╔══╝  ██║  ██║" -ForegroundColor Red
    Write-Host "██║  ██║███████╗██████╔╝" -ForegroundColor Red
    Write-Host "╚═╝  ╚═╝╚══════╝╚═════╝ " -ForegroundColor Red
    Write-Host ""
    Write-Host "RED SYSTEM'S | CLAUDE CODE" -ForegroundColor White
    if ($Subtitle) {
        Write-Host $Subtitle -ForegroundColor DarkGray
    }
    Write-Host ("Workspace: {0}" -f $workspace) -ForegroundColor DarkGray
    Write-Host ("Proxy    : {0}" -f $baseUrl) -ForegroundColor DarkGray
    Write-Host ""
}

function Get-RedModels {
    Write-RedHeader "Carregando catálogo vivo do proxy..."
    try {
        $headers = @{
            "Authorization" = "Bearer $apiKey"
            "X-API-Key" = $apiKey
            "Accept" = "application/json"
        }
        $payload = Invoke-RestMethod -Method Get -Uri $modelEndpoint -Headers $headers -TimeoutSec 40
    } catch {
        Write-Host "Não foi possível buscar os modelos do proxy." -ForegroundColor Red
        Write-Host $_.Exception.Message -ForegroundColor DarkRed
        Write-Host ""
        Write-Host "Verifique a internet, o DNS redsystems.ddns.net e a chave do proxy." -ForegroundColor Yellow
        exit 1
    }

    $items = @()
    foreach ($item in @($payload.data)) {
        $id = [string]$item.id
        if ([string]::IsNullOrWhiteSpace($id)) { continue }

        $red = $item.red
        $kind = [string]$red.kind
        $capabilities = @($red.capabilities)
        if ($capabilities.Count -gt 0 -and -not ($capabilities -contains "chat") -and -not ($capabilities -contains "vision")) {
            continue
        }

        $group = "OLLAMA"
        $vendor = "upstream"
        $name = $id

        if ($id.StartsWith("NIM - ", [StringComparison]::OrdinalIgnoreCase)) {
            $group = "NIM"
            $name = $id.Substring(6).Trim()
            if ($name.Contains("/")) {
                $vendor = $name.Split("/", 2)[0]
            } else {
                $vendor = "nvidia"
            }
        } else {
            $owned = [string]$item.owned_by
            $family = [string]$red.family
            if (-not [string]::IsNullOrWhiteSpace($family)) {
                $vendor = $family
            } elseif (-not [string]::IsNullOrWhiteSpace($owned)) {
                $vendor = $owned
            } else {
                $vendor = "ollama"
            }
        }

        $items += [pscustomobject]@{
            Number = 0
            Id = $id
            Group = $group
            Vendor = $vendor
            Name = $name
            Kind = if ($kind) { $kind } else { "chat" }
            Capabilities = ($capabilities -join ",")
        }
    }

    $ordered = @($items | Sort-Object Group, Vendor, Name)
    for ($i = 0; $i -lt $ordered.Count; $i++) {
        $ordered[$i].Number = $i + 1
    }
    return $ordered
}

function Show-Models {
    param(
        [object[]]$Models,
        [string]$Filter = ""
    )

    Write-RedHeader "Escolha o modelo para iniciar o Claude Code."
    if ($Filter) {
        Write-Host ("Filtro: {0}" -f $Filter) -ForegroundColor Yellow
        Write-Host ""
    }

    $currentGroup = ""
    $currentVendor = ""
    foreach ($model in $Models) {
        if ($model.Group -ne $currentGroup) {
            $currentGroup = $model.Group
            $currentVendor = ""
            Write-Host ""
            Write-Host ("========== {0} ==========" -f $currentGroup) -ForegroundColor Red
        }
        if ($model.Vendor -ne $currentVendor) {
            $currentVendor = $model.Vendor
            Write-Host ""
            Write-Host ("  {0}" -f $currentVendor.ToUpperInvariant()) -ForegroundColor DarkRed
        }

        $line = ("  [{0:000}] {1,-7} {2,-10} {3}" -f $model.Number, $model.Group, $model.Kind, $model.Name)
        Write-Host $line -ForegroundColor White
    }

    Write-Host ""
    Write-Host "Digite o número do modelo." -ForegroundColor Green
    Write-Host "Digite texto para filtrar. R recarrega. Q sai." -ForegroundColor DarkGray
    Write-Host ""
}

function Select-Model {
    param([object[]]$AllModels)

    $filter = ""
    while ($true) {
        $visible = $AllModels
        if ($filter) {
            $needle = $filter.ToLowerInvariant()
            $visible = @($AllModels | Where-Object {
                $_.Id.ToLowerInvariant().Contains($needle) -or
                $_.Vendor.ToLowerInvariant().Contains($needle) -or
                $_.Group.ToLowerInvariant().Contains($needle) -or
                $_.Kind.ToLowerInvariant().Contains($needle) -or
                $_.Capabilities.ToLowerInvariant().Contains($needle)
            })
        }

        Show-Models -Models $visible -Filter $filter
        if ($visible.Count -eq 0) {
            Write-Host "Nenhum modelo encontrado para esse filtro." -ForegroundColor Yellow
        }

        $choice = (Read-Host "RED").Trim()
        if ([string]::IsNullOrWhiteSpace($choice)) { continue }
        if ($choice -match "^[qQ]$") { exit 0 }
        if ($choice -match "^[rR]$") { return $null }
        if ($choice -match "^\d+$") {
            $number = [int]$choice
            $selected = @($AllModels | Where-Object { $_.Number -eq $number } | Select-Object -First 1)
            if ($selected.Count -gt 0) { return $selected[0] }
            Write-Host "Número inválido." -ForegroundColor Yellow
            Start-Sleep -Milliseconds 900
            continue
        }
        $filter = $choice
    }
}

function Start-ClaudeCode {
    param([object]$Model)

    Write-RedHeader ("Iniciando com {0}" -f $Model.Id)

    $claude = Get-Command claude -ErrorAction SilentlyContinue
    if (-not $claude) {
        Write-Host "Claude Code não foi encontrado no PATH." -ForegroundColor Red
        Write-Host ""
        Write-Host "Instale com:" -ForegroundColor Yellow
        Write-Host "  npm install -g @anthropic-ai/claude-code" -ForegroundColor White
        Write-Host ""
        Read-Host "Pressione ENTER para sair"
        exit 1
    }

    $env:ANTHROPIC_BASE_URL = $baseUrl
    $env:ANTHROPIC_AUTH_TOKEN = $apiKey
    $env:ANTHROPIC_API_KEY = $apiKey
    $env:ANTHROPIC_MODEL = $Model.Id
    $env:ANTHROPIC_CUSTOM_MODEL_OPTION = $Model.Id
    $env:ANTHROPIC_CUSTOM_MODEL_OPTION_NAME = "RED $($Model.Group) $($Model.Name)"
    $env:ANTHROPIC_CUSTOM_MODEL_OPTION_DESCRIPTION = "Modelo roteado pelo proxy RED Systems"
    $env:CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS = "1"
    $env:CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"
    $env:DISABLE_TELEMETRY = "1"
    $env:DISABLE_ERROR_REPORTING = "1"

    Set-Location -LiteralPath $workspace
    Write-Host "Tudo OK, iniciando RED." -ForegroundColor Green
    Write-Host ""
    Write-Host ("Modelo: {0}" -f $Model.Id) -ForegroundColor White
    Write-Host ("Pasta : {0}" -f $workspace) -ForegroundColor White
    Write-Host ""

    & claude --model "$($Model.Id)"
    exit $LASTEXITCODE
}

while ($true) {
    $models = Get-RedModels
    if ($models.Count -eq 0) {
        Write-Host "O proxy não retornou modelos compatíveis com chat/visão." -ForegroundColor Red
        exit 1
    }
    $selected = Select-Model -AllModels $models
    if ($null -ne $selected) {
        Start-ClaudeCode -Model $selected
    }
}
