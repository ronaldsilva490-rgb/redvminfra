param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("preseed", "cutover", "verify")]
    [string]$Phase,

    [string]$EnvFile = (Join-Path $PSScriptRoot "migrate_monthly_vm.env")
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $EnvFile)) {
    throw "Arquivo de ambiente nao encontrado: $EnvFile"
}

Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) {
        return
    }
    $parts = $line -split "=", 2
    if ($parts.Count -eq 2) {
        [System.Environment]::SetEnvironmentVariable($parts[0], $parts[1], "Process")
    }
}

$scriptPath = Join-Path $PSScriptRoot "migrate_monthly_vm.py"
if (-not (Test-Path $scriptPath)) {
    throw "Script nao encontrado: $scriptPath"
}

python $scriptPath $Phase
