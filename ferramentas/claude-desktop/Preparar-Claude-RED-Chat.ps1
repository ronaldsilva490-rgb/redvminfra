$ErrorActionPreference = "Stop"

$utf8 = New-Object System.Text.UTF8Encoding($false)
$orgId = "ed7c7df1-5f59-4f8b-86e7-2322495fdabd"
$proxyBaseUrl = "https://redsystems.ddns.net/redproxypro"
$proxyToken = "red"

$models = @(
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

$configPaths = @(
  "$env:APPDATA\Claude\claude_desktop_config.json",
  "$env:APPDATA\Claude-3p\claude_desktop_config.json",
  "$env:LOCALAPPDATA\Claude-3p\claude_desktop_config.json",
  "$env:LOCALAPPDATA\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json",
  "$env:LOCALAPPDATA\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude-3p\claude_desktop_config.json",
  "$env:LOCALAPPDATA\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\Claude-3p\claude_desktop_config.json"
) | Where-Object { Test-Path -LiteralPath $_ }

foreach ($path in $configPaths) {
  $json = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json

  if ($json.PSObject.Properties.Name -contains "sidebarMode") {
    $json.sidebarMode = "chat"
  } else {
    $json | Add-Member -NotePropertyName sidebarMode -NotePropertyValue "chat"
  }

  if ($json.PSObject.Properties.Name -contains "enterpriseConfig") {
    if ($json.enterpriseConfig.PSObject.Properties.Name -contains "inferenceModels") {
      $json.enterpriseConfig.inferenceModels = [string[]]$models
    } else {
      $json.enterpriseConfig | Add-Member -NotePropertyName inferenceModels -NotePropertyValue ([string[]]$models)
    }

    foreach ($key in @(
      "isClaudeCodeForDesktopEnabled",
      "isDesktopExtensionEnabled",
      "isDesktopExtensionDirectoryEnabled",
      "isLocalDevMcpEnabled"
    )) {
      if ($json.enterpriseConfig.PSObject.Properties.Name -contains $key) {
        $json.enterpriseConfig.$key = $false
      } else {
        $json.enterpriseConfig | Add-Member -NotePropertyName $key -NotePropertyValue $false
      }
    }
  }

  [IO.File]::WriteAllText($path, ($json | ConvertTo-Json -Depth 100), $utf8)
}

$roots = @(
  "$env:APPDATA\Claude",
  "$env:APPDATA\Claude-3p",
  "$env:LOCALAPPDATA\Claude-3p",
  "$env:LOCALAPPDATA\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude",
  "$env:LOCALAPPDATA\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude-3p",
  "$env:LOCALAPPDATA\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\Claude-3p"
) | Where-Object { Test-Path -LiteralPath $_ }

foreach ($root in $roots) {
  $libraryDir = Join-Path $root "configLibrary"
  New-Item -ItemType Directory -Force -Path $libraryDir | Out-Null

  $profilePath = Join-Path $libraryDir "$orgId.json"
  if (Test-Path -LiteralPath $profilePath) {
    $profile = Get-Content -Raw -LiteralPath $profilePath | ConvertFrom-Json
  } else {
    $profile = [pscustomobject]@{}
  }

  foreach ($pair in @(
    @("deploymentOrganizationUuid", $orgId),
    @("inferenceProvider", "gateway"),
    @("inferenceGatewayBaseUrl", $proxyBaseUrl),
    @("inferenceGatewayApiKey", $proxyToken),
    @("inferenceGatewayAuthScheme", "bearer"),
    @("disableDeploymentModeChooser", $true),
    @("isClaudeCodeForDesktopEnabled", $false),
    @("isDesktopExtensionEnabled", $false),
    @("isDesktopExtensionDirectoryEnabled", $false),
    @("isLocalDevMcpEnabled", $false)
  )) {
    $key = [string]$pair[0]
    $value = $pair[1]
    if ($profile.PSObject.Properties.Name -contains $key) {
      $profile.$key = $value
    } else {
      $profile | Add-Member -NotePropertyName $key -NotePropertyValue $value
    }
  }

  if ($profile.PSObject.Properties.Name -contains "inferenceModels") {
    $profile.inferenceModels = [string[]]$models
  } else {
    $profile | Add-Member -NotePropertyName inferenceModels -NotePropertyValue ([string[]]$models)
  }

  if ($profile.PSObject.Properties.Name -contains "coworkEgressAllowedHosts") {
    $profile.coworkEgressAllowedHosts = [string[]]@("*")
  } else {
    $profile | Add-Member -NotePropertyName coworkEgressAllowedHosts -NotePropertyValue ([string[]]@("*"))
  }

  [IO.File]::WriteAllText($profilePath, ($profile | ConvertTo-Json -Depth 100), $utf8)

  $metaPath = Join-Path $libraryDir "_meta.json"
  $meta = [pscustomobject]@{
    appliedId = $orgId
    entries = @(
      [pscustomobject]@{
        id = $orgId
        name = "RED Proxy Pro"
      }
    )
  }
  [IO.File]::WriteAllText($metaPath, ($meta | ConvertTo-Json -Depth 100), $utf8)
}
