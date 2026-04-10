Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..\..")
$proxyBaseUrl = "http://redsystems.ddns.net/proxy"
$modelsUrl = "$proxyBaseUrl/v1/models"

$env:ANTHROPIC_AUTH_TOKEN = "ollama"
$env:ANTHROPIC_API_KEY = ""
$env:ANTHROPIC_BASE_URL = $proxyBaseUrl

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function Get-ProxyModels {
    $response = Invoke-RestMethod -Uri $modelsUrl -Method Get -TimeoutSec 30
    $rows = @()
    foreach ($item in ($response.data | Sort-Object id)) {
        $capabilities = @($item.red.capabilities)
        if (-not ($capabilities -contains "chat" -or $capabilities -contains "vision")) {
            continue
        }

        $rows += [PSCustomObject]@{
            Model        = [string]$item.id
            Provider     = [string]$(if ($item.red.provider) { $item.red.provider } elseif ($item.owned_by) { $item.owned_by } else { "" })
            Kind         = [string]$(if ($item.red.kind) { $item.red.kind } else { "" })
            Capabilities = [string]($capabilities -join " | ")
            RouteModel   = [string]$(if ($item.red.route_model) { $item.red.route_model } else { "" })
            Note         = [string]$(if ($item.red.note) { $item.red.note } else { "" })
        }
    }
    return ,$rows
}

function New-ThemeFont([float]$size, [string]$style = "Regular") {
    return New-Object System.Drawing.Font("Segoe UI", $size, [System.Drawing.FontStyle]::$style)
}

function Select-Model {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Models
    )

    $form = New-Object System.Windows.Forms.Form
    $form.Text = "RED Systems Claude Code"
    $form.StartPosition = "CenterScreen"
    $form.Size = New-Object System.Drawing.Size(1120, 760)
    $form.MinimumSize = New-Object System.Drawing.Size(980, 680)
    $form.BackColor = [System.Drawing.Color]::FromArgb(12, 16, 24)
    $form.ForeColor = [System.Drawing.Color]::White
    $form.FormBorderStyle = "Sizable"

    $header = New-Object System.Windows.Forms.Panel
    $header.Dock = "Top"
    $header.Height = 110
    $header.BackColor = [System.Drawing.Color]::FromArgb(18, 22, 32)

    $title = New-Object System.Windows.Forms.Label
    $title.Text = "RED Systems Claude Code"
    $title.Font = New-ThemeFont 20 "Bold"
    $title.ForeColor = [System.Drawing.Color]::White
    $title.AutoSize = $true
    $title.Location = New-Object System.Drawing.Point(20, 16)

    $subtitle = New-Object System.Windows.Forms.Label
    $subtitle.Text = "Escolha o modelo do proxy para abrir o Claude Code."
    $subtitle.Font = New-ThemeFont 10
    $subtitle.ForeColor = [System.Drawing.Color]::FromArgb(168, 180, 198)
    $subtitle.AutoSize = $true
    $subtitle.Location = New-Object System.Drawing.Point(22, 52)

    $status = New-Object System.Windows.Forms.Label
    $status.Text = "Modelos carregados: $($Models.Count) | Base: $proxyBaseUrl"
    $status.Font = New-ThemeFont 9
    $status.ForeColor = [System.Drawing.Color]::FromArgb(255, 111, 111)
    $status.AutoSize = $true
    $status.Location = New-Object System.Drawing.Point(22, 76)

    $header.Controls.AddRange(@($title, $subtitle, $status))
    $form.Controls.Add($header)

    $searchLabel = New-Object System.Windows.Forms.Label
    $searchLabel.Text = "Buscar modelo"
    $searchLabel.Font = New-ThemeFont 10 "Bold"
    $searchLabel.AutoSize = $true
    $searchLabel.Location = New-Object System.Drawing.Point(20, 128)
    $searchLabel.ForeColor = [System.Drawing.Color]::White

    $searchBox = New-Object System.Windows.Forms.TextBox
    $searchBox.Location = New-Object System.Drawing.Point(20, 150)
    $searchBox.Size = New-Object System.Drawing.Size(1060, 30)
    $searchBox.BackColor = [System.Drawing.Color]::FromArgb(15, 20, 31)
    $searchBox.ForeColor = [System.Drawing.Color]::White
    $searchBox.BorderStyle = "FixedSingle"
    $searchBox.Font = New-ThemeFont 10

    $grid = New-Object System.Windows.Forms.DataGridView
    $grid.Location = New-Object System.Drawing.Point(20, 190)
    $grid.Size = New-Object System.Drawing.Size(1060, 470)
    $grid.BackgroundColor = [System.Drawing.Color]::FromArgb(15, 20, 31)
    $grid.BorderStyle = "None"
    $grid.AllowUserToAddRows = $false
    $grid.AllowUserToDeleteRows = $false
    $grid.AllowUserToResizeRows = $false
    $grid.ReadOnly = $true
    $grid.MultiSelect = $false
    $grid.SelectionMode = "FullRowSelect"
    $grid.RowHeadersVisible = $false
    $grid.AutoGenerateColumns = $false
    $grid.EnableHeadersVisualStyles = $false
    $grid.ColumnHeadersDefaultCellStyle.BackColor = [System.Drawing.Color]::FromArgb(26, 33, 46)
    $grid.ColumnHeadersDefaultCellStyle.ForeColor = [System.Drawing.Color]::White
    $grid.ColumnHeadersDefaultCellStyle.Font = New-ThemeFont 10 "Bold"
    $grid.DefaultCellStyle.BackColor = [System.Drawing.Color]::FromArgb(15, 20, 31)
    $grid.DefaultCellStyle.ForeColor = [System.Drawing.Color]::White
    $grid.DefaultCellStyle.SelectionBackColor = [System.Drawing.Color]::FromArgb(166, 32, 40)
    $grid.DefaultCellStyle.SelectionForeColor = [System.Drawing.Color]::White
    $grid.GridColor = [System.Drawing.Color]::FromArgb(36, 45, 61)
    $grid.RowTemplate.Height = 30

    $columns = @(
        @{ Name = "Model"; Header = "Modelo"; Width = 340 },
        @{ Name = "Provider"; Header = "Provider"; Width = 110 },
        @{ Name = "Kind"; Header = "Tipo"; Width = 80 },
        @{ Name = "Capabilities"; Header = "Capabilities"; Width = 170 },
        @{ Name = "RouteModel"; Header = "Route"; Width = 210 },
        @{ Name = "Note"; Header = "Nota"; Width = 120 }
    )

    foreach ($columnInfo in $columns) {
        $column = New-Object System.Windows.Forms.DataGridViewTextBoxColumn
        $column.DataPropertyName = $columnInfo.Name
        $column.Name = $columnInfo.Name
        $column.HeaderText = $columnInfo.Header
        $column.Width = $columnInfo.Width
        $grid.Columns.Add($column) | Out-Null
    }

    $bindingSource = New-Object System.Windows.Forms.BindingSource
    $bindingSource.DataSource = [System.Collections.ArrayList]@($Models)
    $grid.DataSource = $bindingSource

    $selectedLabel = New-Object System.Windows.Forms.Label
    $selectedLabel.Text = "Modelo selecionado: nenhum"
    $selectedLabel.Font = New-ThemeFont 9
    $selectedLabel.ForeColor = [System.Drawing.Color]::FromArgb(168, 180, 198)
    $selectedLabel.AutoSize = $false
    $selectedLabel.Size = New-Object System.Drawing.Size(700, 24)
    $selectedLabel.Location = New-Object System.Drawing.Point(20, 674)

    $cancelButton = New-Object System.Windows.Forms.Button
    $cancelButton.Text = "Cancelar"
    $cancelButton.Size = New-Object System.Drawing.Size(120, 38)
    $cancelButton.Location = New-Object System.Drawing.Point(820, 668)
    $cancelButton.FlatStyle = "Flat"
    $cancelButton.BackColor = [System.Drawing.Color]::FromArgb(22, 29, 41)
    $cancelButton.ForeColor = [System.Drawing.Color]::White

    $openButton = New-Object System.Windows.Forms.Button
    $openButton.Text = "Escolher pasta"
    $openButton.Size = New-Object System.Drawing.Size(160, 38)
    $openButton.Location = New-Object System.Drawing.Point(920, 668)
    $openButton.FlatStyle = "Flat"
    $openButton.BackColor = [System.Drawing.Color]::FromArgb(166, 32, 40)
    $openButton.ForeColor = [System.Drawing.Color]::White
    $openButton.Enabled = $false

    $currentSelection = $null

    function Update-SelectionState {
        if ($grid.CurrentRow -and $grid.CurrentRow.DataBoundItem) {
            $script:currentSelection = $grid.CurrentRow.DataBoundItem
            $selectedLabel.Text = "Modelo selecionado: $($script:currentSelection.Model)"
            $openButton.Enabled = $true
        }
        else {
            $script:currentSelection = $null
            $selectedLabel.Text = "Modelo selecionado: nenhum"
            $openButton.Enabled = $false
        }
    }

    $searchBox.Add_TextChanged({
        $query = $searchBox.Text.Trim().ToLowerInvariant()
        $filtered = if ([string]::IsNullOrWhiteSpace($query)) {
            $Models
        }
        else {
            $Models | Where-Object {
                ($_.Model + " " + $_.Provider + " " + $_.Kind + " " + $_.Capabilities + " " + $_.RouteModel + " " + $_.Note).ToLowerInvariant().Contains($query)
            }
        }
        $bindingSource.DataSource = [System.Collections.ArrayList]@($filtered)
        if ($grid.Rows.Count -gt 0) {
            $grid.ClearSelection()
            $grid.Rows[0].Selected = $true
            $grid.CurrentCell = $grid.Rows[0].Cells[0]
        }
        Update-SelectionState
    })

    $grid.Add_SelectionChanged({ Update-SelectionState })
    $grid.Add_CellDoubleClick({
        param($sender, $eventArgs)
        if ($eventArgs.RowIndex -ge 0) {
            Update-SelectionState
            if ($openButton.Enabled) {
                $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
                $form.Close()
            }
        }
    })

    $cancelButton.Add_Click({
        $form.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
        $form.Close()
    })

    $openButton.Add_Click({
        if ($script:currentSelection) {
            $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
            $form.Close()
        }
    })

    $form.AcceptButton = $openButton
    $form.CancelButton = $cancelButton
    $form.Controls.AddRange(@($searchLabel, $searchBox, $grid, $selectedLabel, $cancelButton, $openButton))

    if ($grid.Rows.Count -gt 0) {
        $grid.Rows[0].Selected = $true
        $grid.CurrentCell = $grid.Rows[0].Cells[0]
        Update-SelectionState
    }

    $dialogResult = $form.ShowDialog()
    if ($dialogResult -ne [System.Windows.Forms.DialogResult]::OK -or -not $script:currentSelection) {
        return $null
    }

    return $script:currentSelection
}

function Select-WorkingFolder {
    param(
        [Parameter(Mandatory = $true)]
        [string]$InitialPath
    )

    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = "Escolha a pasta onde o Claude Code vai trabalhar"
    $dialog.ShowNewFolderButton = $true
    if (Test-Path $InitialPath) {
        $dialog.SelectedPath = $InitialPath
    }

    $result = $dialog.ShowDialog()
    if ($result -ne [System.Windows.Forms.DialogResult]::OK) {
        return $null
    }
    return $dialog.SelectedPath
}

function Start-ClaudeSession {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Model,
        [Parameter(Mandatory = $true)]
        [string]$WorkingFolder
    )

    Write-Host ""
    Write-Host "Modelo: $Model" -ForegroundColor Cyan
    Write-Host "Pasta : $WorkingFolder" -ForegroundColor Cyan
    Write-Host ""

    Set-Location $WorkingFolder
    & claude --model "$Model"
    exit $LASTEXITCODE
}

try {
    $models = Get-ProxyModels
    if (-not $models -or $models.Count -eq 0) {
        Write-Host "Nenhum modelo de chat disponivel no proxy." -ForegroundColor Red
        exit 1
    }

    $selectedModel = Select-Model -Models $models
    if (-not $selectedModel) {
        Write-Host "Selecao cancelada." -ForegroundColor Yellow
        exit 0
    }

    $selectedFolder = Select-WorkingFolder -InitialPath $repoRoot
    if (-not $selectedFolder) {
        Write-Host "Selecao de pasta cancelada." -ForegroundColor Yellow
        exit 0
    }

    Start-ClaudeSession -Model $selectedModel.Model -WorkingFolder $selectedFolder
}
catch {
    Write-Host ""
    Write-Host "ERRO: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    exit 1
}
