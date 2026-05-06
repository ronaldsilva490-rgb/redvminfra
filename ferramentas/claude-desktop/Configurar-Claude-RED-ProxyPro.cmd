@echo off
setlocal EnableExtensions
title Configurar Claude Desktop - RED Proxy Pro
set "RED_SELF=%~f0"

where powershell.exe >nul 2>nul
if errorlevel 1 (
  echo PowerShell nao foi encontrado neste Windows.
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $self=$env:RED_SELF; $raw=[System.IO.File]::ReadAllText($self); $marker='### POWERSHELL_PAYLOAD ###'; $idx=$raw.LastIndexOf($marker); if($idx -lt 0){ throw 'Payload PowerShell nao encontrado.' }; $code=$raw.Substring($idx + $marker.Length); Invoke-Expression $code"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo Configuracao terminou com erro. Codigo: %RC%
) else (
  echo Configuracao concluida.
)
pause
exit /b %RC%

### POWERSHELL_PAYLOAD ###

$ErrorActionPreference = "Stop"

$ProxyBaseUrl = if ($env:RED_PROXY_BASE_URL) { $env:RED_PROXY_BASE_URL.TrimEnd("/") } else { "https://redsystems.ddns.net/redproxypro" }
$ProxyToken = if ($env:RED_PROXY_TOKEN) { $env:RED_PROXY_TOKEN } else { "red" }
$OrgId = "ed7c7df1-5f59-4f8b-86e7-2322495fdabd"
$ProfileName = "RED Proxy Pro"
$Models = @(
    "alibaba/qwen-3.6-max-preview",
    "alibaba/qwen3.5-flash",
    "alibaba/qwen3.5-plus",
    "alibaba/qwen3.6-27b",
    "anthropic/claude-sonnet-4.5",
    "anthropic/claude-sonnet-4.6",
    "deepseek/deepseek-v4-pro",
    "google/gemini-3.1-pro-preview",
    "moonshotai/kimi-k2.5",
    "moonshotai/kimi-k2.6",
    "openai/gpt-5.4-pro",
    "openai/gpt-5.5",
    "openai/gpt-5.5-pro",
    "xai/grok-4.20-multi-agent",
    "xai/grok-4.20-reasoning",
    "xai/grok-4.3",
    "xiaomi/mimo-v2.5",
    "xiaomi/mimo-v2.5-pro",
    "zai/glm-5.1"
)

$EnableWorkspace = if ($env:RED_CLAUDE_ENABLE_WORKSPACE) {
    $env:RED_CLAUDE_ENABLE_WORKSPACE.Trim().ToLowerInvariant() -in @("1", "true", "yes", "on", "sim")
} else {
    $false
}

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ConfiguredFiles = New-Object System.Collections.Generic.List[string]
$Warnings = New-Object System.Collections.Generic.List[string]

function Write-Info($Message) {
    Write-Host "[RED] $Message" -ForegroundColor Cyan
}

function Write-Ok($Message) {
    Write-Host "[OK]  $Message" -ForegroundColor Green
}

function Write-Warn($Message) {
    $script:Warnings.Add($Message) | Out-Null
    Write-Host "[AVISO] $Message" -ForegroundColor Yellow
}

function Get-OptionalFeatureState([string]$Name) {
    try {
        $feature = Get-CimInstance -ClassName Win32_OptionalFeature -Filter "Name='$Name'" -ErrorAction Stop
        if ($null -eq $feature) {
            return "nao encontrado"
        }
        switch ([int]$feature.InstallState) {
            1 { return "ativo" }
            2 { return "desativado" }
            3 { return "ausente" }
            default { return "estado $($feature.InstallState)" }
        }
    } catch {
        return "nao consultado: $($_.Exception.Message)"
    }
}

function Set-JsonProperty($Object, [string]$Name, $Value) {
    if ($Object.PSObject.Properties.Name -contains $Name) {
        $Object.$Name = $Value
    } else {
        $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value -Force
    }
}

function New-EmptyObject {
    return [pscustomobject]@{}
}

function Backup-File([string]$Path) {
    if (!(Test-Path -LiteralPath $Path)) {
        return
    }
    $dir = Split-Path -Parent $Path
    $backupDir = Join-Path $dir "redproxypro-config-backups"
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    $name = Split-Path -Leaf $Path
    Copy-Item -LiteralPath $Path -Destination (Join-Path $backupDir "$name.bak-$script:Stamp") -Force
}

function Read-JsonOrEmpty([string]$Path) {
    if (!(Test-Path -LiteralPath $Path)) {
        return New-EmptyObject
    }
    Backup-File $Path
    $raw = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8).TrimStart([char]0xFEFF)
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return New-EmptyObject
    }
    try {
        return $raw | ConvertFrom-Json
    } catch {
        $dir = Split-Path -Parent $Path
        $backupDir = Join-Path $dir "redproxypro-config-backups"
        New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
        $badName = (Split-Path -Leaf $Path) + ".invalid-$script:Stamp"
        Copy-Item -LiteralPath $Path -Destination (Join-Path $backupDir $badName) -Force
        Write-Warn "JSON invalido encontrado e preservado em backup: $Path"
        return New-EmptyObject
    }
}

function Write-JsonNoBom([string]$Path, $Object) {
    $dir = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    $json = $Object | ConvertTo-Json -Depth 40
    [System.IO.File]::WriteAllText($Path, $json, $script:Utf8NoBom)
    $script:ConfiguredFiles.Add($Path) | Out-Null
}

function Apply-EnterpriseFields($Config) {
    Set-JsonProperty $Config "deploymentOrganizationUuid" $script:OrgId
    Set-JsonProperty $Config "inferenceProvider" "gateway"
    Set-JsonProperty $Config "inferenceGatewayBaseUrl" $script:ProxyBaseUrl
    Set-JsonProperty $Config "inferenceGatewayApiKey" $script:ProxyToken
    Set-JsonProperty $Config "inferenceGatewayAuthScheme" "bearer"
    Set-JsonProperty $Config "inferenceModels" ([string[]]$script:Models)
    Set-JsonProperty $Config "disableDeploymentModeChooser" $true
    Set-JsonProperty $Config "isClaudeCodeForDesktopEnabled" $script:EnableWorkspace
    Set-JsonProperty $Config "isDesktopExtensionEnabled" $script:EnableWorkspace
    Set-JsonProperty $Config "isDesktopExtensionDirectoryEnabled" $script:EnableWorkspace
    Set-JsonProperty $Config "isLocalDevMcpEnabled" $script:EnableWorkspace
    Set-JsonProperty $Config "coworkEgressAllowedHosts" ([string[]]@("*"))
}

function New-ConfigLibraryObject {
    return [pscustomobject]@{
        appliedId = $script:OrgId
        entries = @(
            [pscustomobject]@{
                id = $script:OrgId
                name = $script:ProfileName
            }
        )
    }
}

function Configure-MainConfig([string]$Path) {
    $obj = Read-JsonOrEmpty $Path
    Set-JsonProperty $obj "deploymentMode" "3p"
    if (!($obj.PSObject.Properties.Name -contains "enterpriseConfig") -or $null -eq $obj.enterpriseConfig) {
        Set-JsonProperty $obj "enterpriseConfig" (New-EmptyObject)
    }
    Apply-EnterpriseFields $obj.enterpriseConfig
    Set-JsonProperty $obj "configLibrary" (New-ConfigLibraryObject)
    Write-JsonNoBom $Path $obj
}

function Configure-Library([string]$Root) {
    $libraryDir = Join-Path $Root "configLibrary"
    $profilePath = Join-Path $libraryDir "$script:OrgId.json"
    $metaPath = Join-Path $libraryDir "_meta.json"

    $profile = Read-JsonOrEmpty $profilePath
    Apply-EnterpriseFields $profile
    Write-JsonNoBom $profilePath $profile

    $meta = New-ConfigLibraryObject
    Backup-File $metaPath
    Write-JsonNoBom $metaPath $meta
}

function Add-Root([System.Collections.Generic.List[string]]$Roots, [string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return
    }
    $full = [System.IO.Path]::GetFullPath($Path)
    if (!$Roots.Contains($full)) {
        $Roots.Add($full) | Out-Null
    }
}

function Move-VolatileCache([string]$Base) {
    if (!(Test-Path -LiteralPath $Base)) {
        return
    }
    $resolvedBase = (Resolve-Path -LiteralPath $Base).Path
    $backupRoot = Join-Path $resolvedBase "redproxypro-config-backups\electron-cache-$script:Stamp"
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    foreach ($name in @("Cache", "Code Cache", "GPUCache", "DawnGraphiteCache", "DawnWebGPUCache")) {
        $target = Join-Path $resolvedBase $name
        if (!(Test-Path -LiteralPath $target)) {
            continue
        }
        try {
            $resolvedTarget = (Resolve-Path -LiteralPath $target).Path
            if (!$resolvedTarget.StartsWith($resolvedBase, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Caminho fora da base esperada: $resolvedTarget"
            }
            Move-Item -LiteralPath $resolvedTarget -Destination (Join-Path $backupRoot $name) -Force
        } catch {
            Write-Warn "Nao consegui mover cache '$target'. Feche o Claude e rode de novo se a lista nao atualizar."
        }
    }
}

function Move-WorkspaceState([string]$Base) {
    if ($script:EnableWorkspace -or !(Test-Path -LiteralPath $Base)) {
        return
    }
    $resolvedBase = (Resolve-Path -LiteralPath $Base).Path
    $backupRoot = Join-Path $resolvedBase "redproxypro-config-backups\workspace-state-$script:Stamp"
    $items = @(
        "claude-code-sessions",
        "local-agent-mode-sessions",
        "cowork-enabled-cli-ops.json",
        "git-worktrees.json"
    )
    foreach ($name in $items) {
        $target = Join-Path $resolvedBase $name
        if (!(Test-Path -LiteralPath $target)) {
            continue
        }
        try {
            $resolvedTarget = (Resolve-Path -LiteralPath $target).Path
            if (!$resolvedTarget.StartsWith($resolvedBase, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Caminho fora da base esperada: $resolvedTarget"
            }
            New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
            Move-Item -LiteralPath $resolvedTarget -Destination (Join-Path $backupRoot $name) -Force
        } catch {
            Write-Warn "Nao consegui mover estado de workspace '$target'. Feche o Claude e rode de novo se ainda pedir VMP."
        }
    }
}

function Move-WebUiState([string]$Base) {
    if ($script:EnableWorkspace -or !(Test-Path -LiteralPath $Base)) {
        return
    }
    $resolvedBase = (Resolve-Path -LiteralPath $Base).Path
    $backupRoot = Join-Path $resolvedBase "redproxypro-config-backups\web-ui-state-$script:Stamp"
    $items = @(
        "Local Storage",
        "Session Storage",
        "IndexedDB",
        "WebStorage",
        "blob_storage"
    )
    foreach ($name in $items) {
        $target = Join-Path $resolvedBase $name
        if (!(Test-Path -LiteralPath $target)) {
            continue
        }
        try {
            $resolvedTarget = (Resolve-Path -LiteralPath $target).Path
            if (!$resolvedTarget.StartsWith($resolvedBase, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Caminho fora da base esperada: $resolvedTarget"
            }
            New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
            Move-Item -LiteralPath $resolvedTarget -Destination (Join-Path $backupRoot $name) -Force
        } catch {
            Write-Warn "Nao consegui mover estado web '$target'. Feche o Claude e rode de novo se ainda voltar no modo workspace."
        }
    }
}

function Validate-JsonFiles([string[]]$Roots) {
    $count = 0
    foreach ($root in $Roots) {
        if (!(Test-Path -LiteralPath $root)) {
            continue
        }
        Get-ChildItem -LiteralPath $root -Recurse -File -Filter "*.json" -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -notmatch "redproxypro-config-backups|logs|claude-code-sessions" } |
            ForEach-Object {
                $bytes = [System.IO.File]::ReadAllBytes($_.FullName)
                if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
                    throw "Arquivo JSON com BOM: $($_.FullName)"
                }
                $text = [System.IO.File]::ReadAllText($_.FullName, [System.Text.Encoding]::UTF8)
                $null = $text | ConvertFrom-Json
                $script:ConfiguredFiles.Contains($_.FullName) | Out-Null
                $count++
            }
    }
    return $count
}

Write-Host ""
Write-Host "===============================================" -ForegroundColor DarkRed
Write-Host "  Configurador Claude Desktop - RED Proxy Pro" -ForegroundColor Red
Write-Host "===============================================" -ForegroundColor DarkRed
Write-Host ""
Write-Info "Endpoint: $ProxyBaseUrl"
Write-Info "Modelos: $($Models -join ', ')"
if ($EnableWorkspace) {
    Write-Info "Workspace/Claude Code local: ligado"
} else {
    Write-Info "Workspace/Claude Code local: desligado nas configs"
    Write-Warn "Claude Desktop 1.5354 em gateway 3P ainda abre a tela Cowork por codigo interno. Se o VMP estiver desativado, o aviso do Windows continua aparecendo."
}

$vmpState = Get-OptionalFeatureState "VirtualMachinePlatform"
$hypervisorState = Get-OptionalFeatureState "HypervisorPlatform"
Write-Info "VirtualMachinePlatform: $vmpState"
Write-Info "HypervisorPlatform: $hypervisorState"
if ($vmpState -ne "ativo") {
    Write-Warn "Para usar Claude Desktop com modelos custom/RED Proxy Pro, rode 'Ativar VMP para Claude Desktop.cmd' como administrador e reinicie o Windows."
}

Write-Info "Fechando processos do Claude para evitar cache preso..."
$claudeProcesses = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match "^claude$|^Claude$" }
if ($claudeProcesses) {
    $claudeProcesses | Stop-Process -Force
    Start-Sleep -Seconds 2
    Write-Ok "Claude fechado."
} else {
    Write-Ok "Nenhum processo Claude ativo."
}

$roots = New-Object System.Collections.Generic.List[string]
Add-Root $roots (Join-Path $env:APPDATA "Claude")
Add-Root $roots (Join-Path $env:APPDATA "Claude-3p")
Add-Root $roots (Join-Path $env:LOCALAPPDATA "Claude-3p")

$packagesRoot = Join-Path $env:LOCALAPPDATA "Packages"
if (Test-Path -LiteralPath $packagesRoot) {
    Get-ChildItem -LiteralPath $packagesRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "Claude_*" -or $_.Name -like "*Claude*" } |
        ForEach-Object {
            Add-Root $roots (Join-Path $_.FullName "LocalCache\Roaming\Claude")
            Add-Root $roots (Join-Path $_.FullName "LocalCache\Roaming\Claude-3p")
            Add-Root $roots (Join-Path $_.FullName "LocalCache\Local\Claude-3p")
        }
}

Write-Info "Escrevendo configuracoes..."
foreach ($root in $roots) {
    New-Item -ItemType Directory -Path $root -Force | Out-Null
    Configure-MainConfig (Join-Path $root "claude_desktop_config.json")
    Move-WorkspaceState $root
    Move-WebUiState $root
    if ((Split-Path -Leaf $root) -eq "Claude-3p") {
        Configure-Library $root
    }
}

Write-Info "Limpando caches volateis do Electron..."
Move-VolatileCache (Join-Path $env:LOCALAPPDATA "Claude-3p")
if (Test-Path -LiteralPath $packagesRoot) {
    Get-ChildItem -LiteralPath $packagesRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "Claude_*" -or $_.Name -like "*Claude*" } |
        ForEach-Object {
            Move-VolatileCache (Join-Path $_.FullName "LocalCache\Local\Claude-3p")
        }
}

Write-Info "Testando endpoint do RED Proxy Pro..."
try {
    $headers = @{
        "Authorization" = "Bearer $ProxyToken"
        "Anthropic-Version" = "2023-06-01"
    }
    $catalog = Invoke-RestMethod -Method Get -Uri "$ProxyBaseUrl/v1/models" -Headers $headers -TimeoutSec 25
    $ids = @($catalog.data | ForEach-Object { $_.id })
    if ($ids.Count -lt 1) {
        throw "Catalogo vazio."
    }
    if ($ids[0] -ne $Models[0]) {
        Write-Warn "O primeiro modelo do servidor veio como '$($ids[0])', esperado '$($Models[0])'."
    }
    $gpt = @($catalog.data | Where-Object { $_.id -eq "openai/gpt-5.5" } | Select-Object -First 1)
    $ctx = if ($gpt) { $gpt.context_window } else { "" }
    Write-Ok "Proxy respondeu com $($ids.Count) modelos. GPT 5.5 contexto anunciado: $ctx"
} catch {
    Write-Warn "Nao consegui testar o endpoint agora: $($_.Exception.Message)"
}

Write-Info "Validando JSON sem BOM..."
$jsonCount = Validate-JsonFiles ($roots.ToArray())
Write-Ok "$jsonCount JSONs ativos validos e sem BOM."

Write-Host ""
Write-Ok "Configuracao aplicada em $($ConfiguredFiles.Count) arquivo(s)."
Write-Host "Abra o Claude Desktop agora. A lista deve mostrar:" -ForegroundColor White
foreach ($model in $Models) {
    Write-Host "  - $model" -ForegroundColor Gray
}
Write-Host ""
Write-Host "Dica: para trocar endpoint/token antes de rodar:" -ForegroundColor DarkGray
Write-Host '  set RED_PROXY_BASE_URL=https://redsystems.ddns.net/redproxypro' -ForegroundColor DarkGray
Write-Host '  set RED_PROXY_TOKEN=red' -ForegroundColor DarkGray
Write-Host '  set RED_CLAUDE_ENABLE_WORKSPACE=1  (opcional; Claude Desktop 3P exige VMP de todo jeito)' -ForegroundColor DarkGray

if ($Warnings.Count -gt 0) {
    Write-Host ""
    Write-Host "Avisos:" -ForegroundColor Yellow
    foreach ($warning in $Warnings) {
        Write-Host "  - $warning" -ForegroundColor Yellow
    }
}
