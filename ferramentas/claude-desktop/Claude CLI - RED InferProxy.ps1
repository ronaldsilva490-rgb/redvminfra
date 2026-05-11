$ErrorActionPreference = "Stop"

$utf8 = New-Object System.Text.UTF8Encoding $false
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

$env:ANTHROPIC_BASE_URL = if ($env:RED_INFERPROXY_BASE_URL) { $env:RED_INFERPROXY_BASE_URL.TrimEnd("/") } else { "https://redsystems.ddns.net/inferproxy" }
$env:ANTHROPIC_AUTH_TOKEN = if ($env:RED_INFERPROXY_TOKEN) { $env:RED_INFERPROXY_TOKEN } else { "red" }
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
$env:CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"
$env:CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS = "1"
$env:CLAUDE_CODE_DISABLE_FAST_MODE = "1"
$env:CLAUDE_CODE_SKIP_FAST_MODE_ORG_CHECK = "1"
$env:DISABLE_TELEMETRY = "1"
$env:DISABLE_UPDATES = "1"
$env:TERM = "xterm-256color"
$env:COLORTERM = "truecolor"
$env:FORCE_COLOR = "1"
Remove-Item Env:NO_COLOR -ErrorAction SilentlyContinue

$models = @(
  "Kimi 2.6",
  "Qwen 3.6 Coder 480B",
  "Sonnet 4.6",
  "Opus 4.6"
)

function Write-Header {
  Clear-Host
  Write-Host "=====================================================" -ForegroundColor DarkRed
  Write-Host "  Claude CLI - RED InferProxy" -ForegroundColor Red
  Write-Host "=====================================================" -ForegroundColor DarkRed
  Write-Host "Proxy: " -NoNewline -ForegroundColor DarkGray
  Write-Host $env:ANTHROPIC_BASE_URL -ForegroundColor White
  Write-Host "Token: " -NoNewline -ForegroundColor DarkGray
  Write-Host "red" -ForegroundColor White
  Write-Host ""
}

function Select-Menu([string]$Title, [string[]]$Items) {
  $index = 0
  [Console]::CursorVisible = $false
  try {
    while ($true) {
      Write-Header
      Write-Host $Title -ForegroundColor Yellow
      Write-Host "Use Up/Down ou W/S e Enter. Esc cancela." -ForegroundColor DarkGray
      Write-Host ""
      for ($i = 0; $i -lt $Items.Count; $i++) {
        if ($i -eq $index) {
          Write-Host (" > {0}" -f $Items[$i]) -ForegroundColor Black -BackgroundColor Red
        } else {
          Write-Host ("   {0}" -f $Items[$i]) -ForegroundColor Gray
        }
      }
      $key = [Console]::ReadKey($true)
      switch ($key.Key) {
        'UpArrow' { if ($index -gt 0) { $index-- } else { $index = $Items.Count - 1 } }
        'DownArrow' { if ($index -lt ($Items.Count - 1)) { $index++ } else { $index = 0 } }
        'W' { if ($index -gt 0) { $index-- } else { $index = $Items.Count - 1 } }
        'S' { if ($index -lt ($Items.Count - 1)) { $index++ } else { $index = 0 } }
        'Enter' { return $Items[$index] }
        'Escape' { exit 0 }
      }
    }
  } finally {
    [Console]::CursorVisible = $true
  }
}

function Read-ProjectPath {
  $default = "C:\Projetos"
  Write-Header
  Write-Host "Modelo: " -NoNewline -ForegroundColor DarkGray
  Write-Host $script:SelectedModel -ForegroundColor Yellow
  Write-Host ""
  Write-Host "Abrindo seletor de pasta..." -ForegroundColor Yellow

  try {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = "Escolha a pasta do projeto para Claude CLI"
    $dialog.SelectedPath = $default
    $dialog.ShowNewFolderButton = $true
    $result = $dialog.ShowDialog()
    if ($result -eq [System.Windows.Forms.DialogResult]::OK -and -not [string]::IsNullOrWhiteSpace($dialog.SelectedPath)) {
      return (Resolve-Path -LiteralPath $dialog.SelectedPath).Path
    }
  } catch {
    Start-Sleep -Seconds 1
  }

  return $default
}

function Ensure-ClaudeCli {
  $cmd = Get-Command claude -ErrorAction SilentlyContinue
  if ($cmd) { return }
  $localClaude = Join-Path $env:USERPROFILE ".local\bin\claude.exe"
  if (Test-Path -LiteralPath $localClaude) {
    $env:PATH = (Split-Path -Parent $localClaude) + ";" + $env:PATH
    return
  }
  Write-Header
  Write-Host "Claude CLI nao foi encontrado no PATH." -ForegroundColor Red
  Write-Host "Fallback esperado: $localClaude" -ForegroundColor Gray
  pause
  exit 1
}

Ensure-ClaudeCli
$script:SelectedModel = Select-Menu -Title "Escolha o modelo" -Items $models
$sessionMode = Select-Menu -Title "Escolha a sessao" -Items @(
  "Nova conversa",
  "Continuar ultima conversa nesta pasta",
  "Escolher conversa antiga"
)
$projectPath = Read-ProjectPath

$env:ANTHROPIC_MODEL = $script:SelectedModel
$env:ANTHROPIC_SMALL_FAST_MODEL = $script:SelectedModel
$env:ANTHROPIC_DEFAULT_SONNET_MODEL = $script:SelectedModel
$env:ANTHROPIC_DEFAULT_OPUS_MODEL = $script:SelectedModel
$env:ANTHROPIC_DEFAULT_HAIKU_MODEL = $script:SelectedModel
$env:CLAUDE_CODE_SUBAGENT_MODEL = $script:SelectedModel

$runtimeSettings = Join-Path $env:TEMP ("claude-red-inferproxy-" + [guid]::NewGuid().ToString() + ".json")
$runtimeConfig = @{
  env = @{
    ANTHROPIC_BASE_URL = $env:ANTHROPIC_BASE_URL
    ANTHROPIC_AUTH_TOKEN = $env:ANTHROPIC_AUTH_TOKEN
    ANTHROPIC_MODEL = $script:SelectedModel
    ANTHROPIC_SMALL_FAST_MODEL = $script:SelectedModel
    ANTHROPIC_DEFAULT_SONNET_MODEL = $script:SelectedModel
    ANTHROPIC_DEFAULT_OPUS_MODEL = $script:SelectedModel
    ANTHROPIC_DEFAULT_HAIKU_MODEL = $script:SelectedModel
    CLAUDE_CODE_SUBAGENT_MODEL = $script:SelectedModel
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"
    CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS = "1"
    CLAUDE_CODE_MAX_RETRIES = "2"
    API_TIMEOUT_MS = "600000"
  }
  permissions = @{
    defaultMode = "dontAsk"
  }
  enabledPlugins = @{
    "frontend-design@claude-plugins-official" = $true
    "superpowers@claude-plugins-official" = $true
    "playwright@claude-plugins-official" = $true
    "code-review@claude-plugins-official" = $true
    "fastly-agent-toolkit@claude-plugins-official" = $true
  }
  model = $script:SelectedModel
  skipDangerousModePermissionPrompt = $true
  language = "PORTUGUES DO BRASIL"
  theme = "dark-daltonized"
  editorMode = "normal"
}
Set-Content -LiteralPath $runtimeSettings -Value ($runtimeConfig | ConvertTo-Json -Depth 20) -Encoding UTF8

Set-Location -LiteralPath $projectPath

$redSystemPrompt = @'
Voce esta rodando no Claude Code via RED InferProxy.

Regras operacionais obrigatorias:
- Skills/plugins sao parte do fluxo normal do Claude Code, nao sao "ferramentas de workspace".
- Quando uma skill/plugin relevante existir, invoque a ferramenta Skill antes de responder ou executar. Para pedidos de frontend, design, paginas, interfaces ou componentes, use frontend-design:frontend-design. Para trabalho criativo/de implementacao, use tambem a skill de processo adequada de superpowers.
- Para saudacoes, identidade, conversa casual, perguntas conceituais simples ou pedidos de explicacao, responda diretamente em texto.
- Nunca use Bash, Read, Write, Edit, Glob, Grep, WebFetch, WebSearch, TodoWrite ou ferramentas de workspace para produzir uma resposta textual que voce ja sabe responder.
- Nunca use Bash(echo ...) para responder ao usuario.
- Use ferramentas somente quando a tarefa exigir inspecionar arquivos, modificar arquivos, executar testes, consultar rede ou operar o workspace.
- Quando usar ferramenta, use a ferramenta real para avancar a tarefa; nao use ferramenta como forma de "imprimir" a resposta.
- Se o usuario perguntar quem e voce, responda diretamente que voce e o Claude Code rodando atraves do RED InferProxy no ambiente do usuario.
- Responda em portugues do Brasil por padrao.
'@

Clear-Host
$commonArgs = @(
  "--settings", $runtimeSettings,
  "--setting-sources", "user",
  "--dangerously-skip-permissions",
  "--permission-mode", "bypassPermissions",
  "--effort", "max",
  "--append-system-prompt", $redSystemPrompt,
  "--model", $script:SelectedModel
)

try {
  switch ($sessionMode) {
    "Continuar ultima conversa nesta pasta" {
      claude @commonArgs --continue
    }
    "Escolher conversa antiga" {
      claude @commonArgs --resume
    }
    default {
      claude @commonArgs
    }
  }
} finally {
  Remove-Item -LiteralPath $runtimeSettings -Force -ErrorAction SilentlyContinue
}
