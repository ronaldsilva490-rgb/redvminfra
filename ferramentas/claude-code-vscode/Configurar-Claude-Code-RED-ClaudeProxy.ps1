$ErrorActionPreference = "Stop"

$utf8 = New-Object System.Text.UTF8Encoding($false)

$proxyUrl = "https://redsystems.ddns.net/redclaudeproxy"
$proxyToken = "red"
$defaultModel = "claude-red-devstral-medium"

$envMap = [ordered]@{
  "ANTHROPIC_BASE_URL" = $proxyUrl
  "ANTHROPIC_API_KEY" = $proxyToken
  "ANTHROPIC_AUTH_TOKEN" = $proxyToken
  "ANTHROPIC_MODEL" = $defaultModel
  "ANTHROPIC_DEFAULT_SONNET_MODEL" = "claude-red-devstral-medium"
  "ANTHROPIC_DEFAULT_OPUS_MODEL" = "claude-red-nim-glm51"
  "ANTHROPIC_DEFAULT_HAIKU_MODEL" = "claude-red-mistral-small"
  "ANTHROPIC_CUSTOM_MODEL_OPTION" = "claude-red-nim-glm51"
  "ANTHROPIC_CUSTOM_MODEL_OPTION_NAME" = "RED NIM GLM 5.1"
  "ANTHROPIC_CUSTOM_MODEL_OPTION_DESCRIPTION" = "RED Claude Proxy"
  "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC" = "1"
  "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS" = "1"
  "CLAUDE_CODE_MAX_RETRIES" = "2"
  "API_TIMEOUT_MS" = "600000"
}

function Read-JsonOrEmpty($path) {
  if (Test-Path -LiteralPath $path) {
    $raw = Get-Content -Raw -LiteralPath $path
    if ($raw.Trim()) {
      return $raw | ConvertFrom-Json
    }
  }
  return [pscustomobject]@{}
}

function Set-JsonProperty($object, $name, $value) {
  if ($object.PSObject.Properties.Name -contains $name) {
    $object.$name = $value
  } else {
    $object | Add-Member -NotePropertyName $name -NotePropertyValue $value
  }
}

$claudeDir = Join-Path $env:USERPROFILE ".claude"
New-Item -ItemType Directory -Force -Path $claudeDir | Out-Null

$claudeSettingsPath = Join-Path $claudeDir "settings.json"
if (Test-Path -LiteralPath $claudeSettingsPath) {
  Copy-Item -LiteralPath $claudeSettingsPath -Destination "$claudeSettingsPath.bak-redproxy" -Force
}

$claudeSettings = Read-JsonOrEmpty $claudeSettingsPath
Set-JsonProperty $claudeSettings '$schema' "https://json.schemastore.org/claude-code-settings.json"
Set-JsonProperty $claudeSettings "model" $defaultModel

if (-not ($claudeSettings.PSObject.Properties.Name -contains "env") -or $null -eq $claudeSettings.env) {
  Set-JsonProperty $claudeSettings "env" ([pscustomobject]@{})
}

foreach ($name in $envMap.Keys) {
  Set-JsonProperty $claudeSettings.env $name $envMap[$name]
}

[IO.File]::WriteAllText($claudeSettingsPath, ($claudeSettings | ConvertTo-Json -Depth 100), $utf8)

$vscodeSettingsPath = Join-Path $env:APPDATA "Code\User\settings.json"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $vscodeSettingsPath) | Out-Null

if (Test-Path -LiteralPath $vscodeSettingsPath) {
  Copy-Item -LiteralPath $vscodeSettingsPath -Destination "$vscodeSettingsPath.bak-redproxy" -Force
}

$vscodeSettings = Read-JsonOrEmpty $vscodeSettingsPath
Set-JsonProperty $vscodeSettings "claudeCode.disableLoginPrompt" $true
Set-JsonProperty $vscodeSettings "claudeCode.preferredLocation" "panel"

$existingVars = @{}
if ($vscodeSettings.PSObject.Properties.Name -contains "claudeCode.environmentVariables") {
  foreach ($item in $vscodeSettings.'claudeCode.environmentVariables') {
    if ($item.name) {
      $existingVars[$item.name] = [string]$item.value
    }
  }
}

foreach ($name in $envMap.Keys) {
  $existingVars[$name] = $envMap[$name]
}

$envArray = @(
  foreach ($name in ($existingVars.Keys | Sort-Object)) {
    [pscustomobject]@{
      name = $name
      value = $existingVars[$name]
    }
  }
)

Set-JsonProperty $vscodeSettings "claudeCode.environmentVariables" $envArray
[IO.File]::WriteAllText($vscodeSettingsPath, ($vscodeSettings | ConvertTo-Json -Depth 100), $utf8)

Write-Host "Claude Code configurado para RED Claude Proxy:"
Write-Host "  $proxyUrl"
Write-Host "  modelo padrao: $defaultModel"
