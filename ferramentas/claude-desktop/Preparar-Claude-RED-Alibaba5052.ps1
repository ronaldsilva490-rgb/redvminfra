$ErrorActionPreference = "Stop"

$utf8 = New-Object System.Text.UTF8Encoding($false)
$orgId = "5cece2be-9005-4773-aafb-315a49634644"
$proxyBaseUrl = if ($env:RED_ALIBABA_CLAUDE_BASE_URL) { $env:RED_ALIBABA_CLAUDE_BASE_URL.TrimEnd("/") } else { "https://redsystems.ddns.net:5052" }
$proxyToken = if ($env:RED_ALIBABA_CLAUDE_TOKEN) { $env:RED_ALIBABA_CLAUDE_TOKEN } else { "red" }
$profileName = "RED Alibaba Claude 5052"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

$fallbackModels = @(
  "ALI-SG/qwen-coder-plus",
  "ALI-SG/qwen3.6-plus",
  "ALI-SG/qwen3.6-max-preview",
  "ALI-SG/qwen3-coder-next",
  "ALI-US/qwen3-coder-plus",
  "ALI-US/deepseek-v4-pro",
  "ALI-US/deepseek-v4-flash",
  "ALI-US/kimi-k2.5"
)

function Write-Info($message) { Write-Host "[RED] $message" -ForegroundColor Cyan }
function Write-Ok($message) { Write-Host "[OK]  $message" -ForegroundColor Green }
function Write-Warn($message) { Write-Host "[AVISO] $message" -ForegroundColor Yellow }

function Set-JsonProperty($object, [string]$name, $value) {
  if ($object.PSObject.Properties.Name -contains $name) {
    $object.$name = $value
  } else {
    $object | Add-Member -NotePropertyName $name -NotePropertyValue $value -Force
  }
}

function New-EmptyObject {
  return [pscustomobject]@{}
}

function Backup-File([string]$path) {
  if (!(Test-Path -LiteralPath $path)) { return }
  $dir = Split-Path -Parent $path
  $backupDir = Join-Path $dir "redalibabaclaude-config-backups"
  New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
  $name = Split-Path -Leaf $path
  Copy-Item -LiteralPath $path -Destination (Join-Path $backupDir "$name.bak-$script:stamp") -Force
}

function Read-JsonOrEmpty([string]$path) {
  if (!(Test-Path -LiteralPath $path)) { return New-EmptyObject }
  Backup-File $path
  $raw = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8).TrimStart([char]0xFEFF)
  if ([string]::IsNullOrWhiteSpace($raw)) { return New-EmptyObject }
  try {
    return $raw | ConvertFrom-Json
  } catch {
    $dir = Split-Path -Parent $path
    $backupDir = Join-Path $dir "redalibabaclaude-config-backups"
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    Copy-Item -LiteralPath $path -Destination (Join-Path $backupDir ((Split-Path -Leaf $path) + ".invalid-$script:stamp")) -Force
    Write-Warn "JSON invalido preservado em backup: $path"
    return New-EmptyObject
  }
}

function Write-JsonNoBom([string]$path, $object) {
  $dir = Split-Path -Parent $path
  New-Item -ItemType Directory -Path $dir -Force | Out-Null
  [System.IO.File]::WriteAllText($path, ($object | ConvertTo-Json -Depth 80), $script:utf8)
}

function Add-Root([System.Collections.Generic.List[string]]$roots, [string]$path) {
  if ([string]::IsNullOrWhiteSpace($path)) { return }
  $full = [System.IO.Path]::GetFullPath($path)
  if (!$roots.Contains($full)) { $roots.Add($full) | Out-Null }
}

function Get-ProxyModels {
  try {
    $headers = @{
      "Authorization" = "Bearer $script:proxyToken"
      "Anthropic-Version" = "2023-06-01"
    }
    $catalog = Invoke-RestMethod -Method Get -Uri "$script:proxyBaseUrl/v1/models" -Headers $headers -TimeoutSec 25
    $ids = @(
      $catalog.data |
        Where-Object { $_.id } |
        ForEach-Object { [string]$_.id } |
        Sort-Object -Unique
    )
    if ($ids.Count -ge 1) { return [string[]]$ids }
    Write-Warn "Catalogo do RED Alibaba Claude veio vazio; usando fallback local."
  } catch {
    Write-Warn "Nao consegui consultar $script:proxyBaseUrl agora: $($_.Exception.Message)"
  }
  return [string[]]$script:fallbackModels
}

function Apply-EnterpriseFields($config, [string[]]$models) {
  Set-JsonProperty $config "deploymentOrganizationUuid" $script:orgId
  Set-JsonProperty $config "inferenceProvider" "gateway"
  Set-JsonProperty $config "inferenceGatewayBaseUrl" $script:proxyBaseUrl
  Set-JsonProperty $config "inferenceGatewayApiKey" $script:proxyToken
  Set-JsonProperty $config "inferenceGatewayAuthScheme" "bearer"
  Set-JsonProperty $config "inferenceModels" ([string[]]$models)
  Set-JsonProperty $config "disableDeploymentModeChooser" $true
  Set-JsonProperty $config "isClaudeCodeForDesktopEnabled" $false
  Set-JsonProperty $config "isDesktopExtensionEnabled" $false
  Set-JsonProperty $config "isDesktopExtensionDirectoryEnabled" $false
  Set-JsonProperty $config "isLocalDevMcpEnabled" $false
  Set-JsonProperty $config "coworkEgressAllowedHosts" ([string[]]@("*"))
}

function New-ConfigLibraryObject {
  return [pscustomobject]@{
    appliedId = $script:orgId
    entries = @(
      [pscustomobject]@{
        id = $script:orgId
        name = $script:profileName
      }
    )
  }
}

function Configure-MainConfig([string]$path, [string[]]$models) {
  $obj = Read-JsonOrEmpty $path
  Set-JsonProperty $obj "deploymentMode" "3p"
  Set-JsonProperty $obj "sidebarMode" "chat"
  if (!($obj.PSObject.Properties.Name -contains "enterpriseConfig") -or $null -eq $obj.enterpriseConfig) {
    Set-JsonProperty $obj "enterpriseConfig" (New-EmptyObject)
  }
  Apply-EnterpriseFields $obj.enterpriseConfig $models
  Set-JsonProperty $obj "configLibrary" (New-ConfigLibraryObject)
  Write-JsonNoBom $path $obj
}

function Configure-Library([string]$root, [string[]]$models) {
  $libraryDir = Join-Path $root "configLibrary"
  $profilePath = Join-Path $libraryDir "$script:orgId.json"
  $metaPath = Join-Path $libraryDir "_meta.json"
  New-Item -ItemType Directory -Path $libraryDir -Force | Out-Null

  $profile = Read-JsonOrEmpty $profilePath
  Apply-EnterpriseFields $profile $models
  Write-JsonNoBom $profilePath $profile
  Backup-File $metaPath
  Write-JsonNoBom $metaPath (New-ConfigLibraryObject)
}

Write-Host ""
Write-Host "=================================================" -ForegroundColor DarkRed
Write-Host "  Claude Desktop - RED Alibaba Claude :5052" -ForegroundColor Red
Write-Host "=================================================" -ForegroundColor DarkRed
Write-Host ""
Write-Info "Endpoint: $proxyBaseUrl"
Write-Info "Este preparo preserva Local Storage, Session Storage, IndexedDB e pastas de sessoes."

$models = Get-ProxyModels
Write-Info "Modelos configurados: $($models.Count)"

Write-Info "Fechando Claude para gravar configuracao sem cache preso..."
Get-Process -ErrorAction SilentlyContinue |
  Where-Object { $_.ProcessName -match "^claude$|^Claude$" } |
  Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800

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

foreach ($root in $roots) {
  New-Item -ItemType Directory -Path $root -Force | Out-Null
  Configure-MainConfig (Join-Path $root "claude_desktop_config.json") $models
  Configure-Library $root $models
}

Write-Ok "Configuracao aplicada sem limpar sessoes."
Write-Host "Modelos publicados:" -ForegroundColor White
$models | ForEach-Object { Write-Host "  - $_" -ForegroundColor Gray }
