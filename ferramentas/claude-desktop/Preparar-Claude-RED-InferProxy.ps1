param(
  [switch]$NoLaunch,
  [switch]$ForceClose
)

$ErrorActionPreference = "Stop"

$utf8 = New-Object System.Text.UTF8Encoding($false)
$orgId = "7d8a711a-0841-4ec4-90fd-79d4522d5066"
$proxyBaseUrl = if ($env:RED_INFERPROXY_BASE_URL) { $env:RED_INFERPROXY_BASE_URL.TrimEnd("/") } else { "https://redsystems.ddns.net/inferproxy" }
$proxyToken = if ($env:RED_INFERPROXY_TOKEN) { $env:RED_INFERPROXY_TOKEN } else { "red" }
$profileName = "RED InferProxy"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

$fallbackModels = @(
  "Kimi 2.6",
  "Qwen 3.6 Coder 480B",
  "Sonnet 4.6",
  "Opus 4.6"
)

function Write-Info($message) { Write-Host "[InferProxy] $message" -ForegroundColor Cyan }
function Write-Ok($message) { Write-Host "[OK]         $message" -ForegroundColor Green }
function Write-Warn($message) { Write-Host "[AVISO]      $message" -ForegroundColor Yellow }

function Set-JsonProperty($object, [string]$name, $value) {
  if ($object.PSObject.Properties.Name -contains $name) {
    $object.$name = $value
  } else {
    $object | Add-Member -NotePropertyName $name -NotePropertyValue $value -Force
  }
}

function Remove-JsonProperty($object, [string]$name) {
  if ($object -and $object.PSObject.Properties.Name -contains $name) {
    $object.PSObject.Properties.Remove($name)
  }
}

function New-EmptyObject {
  return [pscustomobject]@{}
}

function Backup-File([string]$path) {
  if (!(Test-Path -LiteralPath $path)) { return }
  $dir = Split-Path -Parent $path
  $backupDir = Join-Path $dir "inferproxy-config-backups"
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
    $backupDir = Join-Path $dir "inferproxy-config-backups"
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
    $seen = @{}
    $ids = @(
      $catalog.data |
        Where-Object { $_.id } |
        ForEach-Object {
          $id = [string]$_.id
          if (!$seen.ContainsKey($id)) {
            $seen[$id] = $true
            $id
          }
        }
    )
    if ($ids.Count -ge 1) { return [string[]]$ids }
    Write-Warn "Catalogo do InferProxy veio vazio; usando fallback local."
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
  Set-JsonProperty $config "isClaudeCodeForDesktopEnabled" $true
  Set-JsonProperty $config "isDesktopExtensionEnabled" $true
  Set-JsonProperty $config "isDesktopExtensionDirectoryEnabled" $true
  Set-JsonProperty $config "isLocalDevMcpEnabled" $true
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
  if (!($obj.PSObject.Properties.Name -contains "preferences") -or $null -eq $obj.preferences) {
    Set-JsonProperty $obj "preferences" (New-EmptyObject)
  }
  Set-JsonProperty $obj.preferences "coworkWebSearchEnabled" $true
  Set-JsonProperty $obj.preferences "bypassPermissionsModeEnabled" $true
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

  $cleanupDir = Join-Path $libraryDir "inferproxy-cleaned-profiles-$script:stamp"
  Get-ChildItem -LiteralPath $libraryDir -File -ErrorAction SilentlyContinue |
    Where-Object {
      $_.Name -ne "_meta.json" -and
      $_.Name -ne "$script:orgId.json" -and
      ($_.Extension -eq ".json" -or $_.Name -like "*.json.disabled")
    } |
    ForEach-Object {
      New-Item -ItemType Directory -Path $cleanupDir -Force | Out-Null
      Move-Item -LiteralPath $_.FullName -Destination (Join-Path $cleanupDir $_.Name) -Force
    }

  $profile = Read-JsonOrEmpty $profilePath
  Apply-EnterpriseFields $profile $models
  Write-JsonNoBom $profilePath $profile
  Backup-File $metaPath
  Write-JsonNoBom $metaPath (New-ConfigLibraryObject)
}

function Get-PreferredCodeModel([string[]]$models) {
  foreach ($candidate in @("Sonnet 4.6", "Opus 4.6", "Qwen 3.6 Coder 480B", "Kimi 2.6")) {
    if ($models -contains $candidate) { return $candidate }
  }
  if ($models.Count -gt 0) { return $models[0] }
  return "Sonnet 4.6"
}

function Configure-ClaudeCodeSettings([string[]]$models) {
  $path = Join-Path $env:USERPROFILE ".claude\settings.json"
  $obj = Read-JsonOrEmpty $path
  $preferred = Get-PreferredCodeModel $models

  if (!($obj.PSObject.Properties.Name -contains "env") -or $null -eq $obj.env) {
    Set-JsonProperty $obj "env" (New-EmptyObject)
  }

  Remove-JsonProperty $obj.env "ANTHROPIC_API_KEY"
  Remove-JsonProperty $obj.env "ANTHROPIC_CUSTOM_MODEL_OPTION"
  Remove-JsonProperty $obj.env "ANTHROPIC_CUSTOM_MODEL_OPTION_NAME"
  Remove-JsonProperty $obj.env "ANTHROPIC_CUSTOM_MODEL_OPTION_DESCRIPTION"
  Set-JsonProperty $obj.env "ANTHROPIC_BASE_URL" $script:proxyBaseUrl
  Set-JsonProperty $obj.env "ANTHROPIC_AUTH_TOKEN" $script:proxyToken
  Set-JsonProperty $obj.env "ANTHROPIC_MODEL" $preferred
  Set-JsonProperty $obj.env "ANTHROPIC_SMALL_FAST_MODEL" $preferred
  Set-JsonProperty $obj.env "ANTHROPIC_DEFAULT_SONNET_MODEL" $preferred
  Set-JsonProperty $obj.env "ANTHROPIC_DEFAULT_OPUS_MODEL" $preferred
  Set-JsonProperty $obj.env "ANTHROPIC_DEFAULT_HAIKU_MODEL" $preferred
  Set-JsonProperty $obj.env "CLAUDE_CODE_SUBAGENT_MODEL" $preferred
  Set-JsonProperty $obj.env "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC" "1"
  Set-JsonProperty $obj.env "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS" "1"
  Set-JsonProperty $obj.env "CLAUDE_CODE_DISABLE_FAST_MODE" "1"
  Set-JsonProperty $obj.env "CLAUDE_CODE_SKIP_FAST_MODE_ORG_CHECK" "1"
  Set-JsonProperty $obj.env "CLAUDE_CODE_MAX_RETRIES" "2"
  Set-JsonProperty $obj.env "API_TIMEOUT_MS" "600000"

  Set-JsonProperty $obj "model" $preferred
  Set-JsonProperty $obj "permissions" ([pscustomobject]@{ defaultMode = "dontAsk" })
  Set-JsonProperty $obj "skipDangerousModePermissionPrompt" $true
  Set-JsonProperty $obj "language" "PORTUGUES DO BRASIL"
  Set-JsonProperty $obj "theme" "dark-daltonized"
  Set-JsonProperty $obj "editorMode" "normal"
  Set-JsonProperty $obj "enabledPlugins" ([pscustomobject]@{
    "frontend-design@claude-plugins-official" = $true
    "superpowers@claude-plugins-official" = $true
    "playwright@claude-plugins-official" = $true
    "code-review@claude-plugins-official" = $true
    "fastly-agent-toolkit@claude-plugins-official" = $true
  })

  Write-JsonNoBom $path $obj
  Write-Ok "Claude Code settings apontando para o InferProxy."
}

function Test-InferProxyGateway([string[]]$models) {
  try {
    $headers = @{
      "Authorization" = "Bearer $script:proxyToken"
      "Content-Type" = "application/json"
      "Anthropic-Version" = "2023-06-01"
    }
    foreach ($model in $models) {
      $body = @{
        model = $model
        max_tokens = 32
        messages = @(
          @{
            role = "user"
            content = "Responda exatamente: OK"
          }
        )
      } | ConvertTo-Json -Depth 20
      $response = Invoke-RestMethod -Method Post -Uri "$script:proxyBaseUrl/v1/messages" -Headers $headers -Body $body -TimeoutSec 60
      $text = [string]$response.content[0].text
      if ($text -notmatch "OK") {
        throw "$model respondeu inesperado: $text"
      }
      Write-Ok "InferProxy respondeu em /v1/messages com $model."
    }
  } catch {
    Write-Warn "Nao consegui validar /v1/messages agora: $($_.Exception.Message)"
    Write-Warn "Vou aplicar a configuracao mesmo assim."
  }
}

function Get-ClaudeDesktopProcesses {
  $desktopExeCandidates = @(
    "C:\Projetos\ClaudeREDDesktop\app\Claude.exe",
    (Join-Path $env:LOCALAPPDATA "Programs\Claude\Claude.exe")
  ) |
    Where-Object { $_ } |
    ForEach-Object { [System.IO.Path]::GetFullPath($_).ToLowerInvariant() }

  Get-Process -Name claude -ErrorAction SilentlyContinue |
    Where-Object {
      $path = ""
      try { $path = [string]$_.Path } catch { $path = "" }
      if ($path) {
        $full = [System.IO.Path]::GetFullPath($path).ToLowerInvariant()
        $desktopExeCandidates -contains $full
      } else {
        $true
      }
    }
}

Write-Host ""
Write-Host "=================================================" -ForegroundColor DarkRed
Write-Host "  Claude Desktop - RED InferProxy" -ForegroundColor Red
Write-Host "=================================================" -ForegroundColor DarkRed
Write-Host ""
Write-Info "Endpoint: $proxyBaseUrl"
Write-Info "Configurando sem apagar Local Storage, Session Storage, IndexedDB ou historico."

$models = Get-ProxyModels
Write-Info "Modelos configurados: $($models.Count)"
Test-InferProxyGateway $models
Configure-ClaudeCodeSettings $models

$running = @(Get-ClaudeDesktopProcesses)
if ($running.Count -gt 0) {
  if ($NoLaunch -and !$ForceClose) {
    Write-Warn "Claude Desktop esta aberto. Vou gravar os JSONs sem fechar; reinicie o app para usar esta config."
  } elseif ($ForceClose) {
    Write-Warn "Fechando Claude Desktop para limpar configuracoes antigas."
    $running | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 800
  } else {
    Write-Warn "Claude Desktop esta aberto. Para a configuracao pegar na hora, ele precisa reiniciar."
    $answer = Read-Host "Fechar Claude agora para aplicar? [S/N]"
    if ($answer -match "^[sS]") {
      $running | Stop-Process -Force -ErrorAction SilentlyContinue
      Start-Sleep -Milliseconds 800
    } else {
      Write-Warn "Vou gravar os JSONs, mas talvez o app aberto continue usando a config antiga ate reiniciar."
    }
  }
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

foreach ($root in $roots) {
  New-Item -ItemType Directory -Path $root -Force | Out-Null
  Configure-MainConfig (Join-Path $root "claude_desktop_config.json") $models
  Configure-Library $root $models
}

Write-Ok "Configuracao RED InferProxy aplicada. Perfis anteriores ficaram em backup."
Write-Host "Modelos no seletor:" -ForegroundColor White
$models | ForEach-Object { Write-Host "  - $_" -ForegroundColor Gray }

if ($NoLaunch) { exit 0 }

$claudeExe = "C:\Projetos\ClaudeREDDesktop\app\Claude.exe"
if (!(Test-Path -LiteralPath $claudeExe)) {
  $claudeExe = Join-Path $env:LOCALAPPDATA "Programs\Claude\Claude.exe"
}

if (!(Test-Path -LiteralPath $claudeExe)) {
  Write-Warn "Claude Desktop nao encontrado para abrir automaticamente."
  exit 1
}

Start-Process -FilePath $claudeExe -ArgumentList "--no-sandbox"
