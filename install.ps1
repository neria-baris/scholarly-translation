$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Scholarly Translation - Setup'
$form.Size = New-Object System.Drawing.Size(560, 460)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false

$titleLabel = New-Object System.Windows.Forms.Label
$titleLabel.Text = 'Scholarly Translation - local setup'
$titleLabel.Font = New-Object System.Drawing.Font('Segoe UI', 12, [System.Drawing.FontStyle]::Bold)
$titleLabel.Location = New-Object System.Drawing.Point(20, 15)
$titleLabel.Size = New-Object System.Drawing.Size(500, 26)
$form.Controls.Add($titleLabel)

$subLabel = New-Object System.Windows.Forms.Label
$subLabel.Text = 'Installs Python dependencies into a local .venv and creates a desktop shortcut. No admin rights required.'
$subLabel.Location = New-Object System.Drawing.Point(20, 44)
$subLabel.Size = New-Object System.Drawing.Size(500, 34)
$form.Controls.Add($subLabel)

$progress = New-Object System.Windows.Forms.ProgressBar
$progress.Location = New-Object System.Drawing.Point(20, 82)
$progress.Size = New-Object System.Drawing.Size(500, 22)
$progress.Minimum = 0
$progress.Maximum = 100
$form.Controls.Add($progress)

$log = New-Object System.Windows.Forms.TextBox
$log.Multiline = $true
$log.ScrollBars = 'Vertical'
$log.ReadOnly = $true
$log.Location = New-Object System.Drawing.Point(20, 114)
$log.Size = New-Object System.Drawing.Size(500, 260)
$log.Font = New-Object System.Drawing.Font('Consolas', 9)
$log.BackColor = [System.Drawing.Color]::White
$form.Controls.Add($log)

$runButton = New-Object System.Windows.Forms.Button
$runButton.Text = 'Run now'
$runButton.Location = New-Object System.Drawing.Point(20, 385)
$runButton.Size = New-Object System.Drawing.Size(100, 32)
$runButton.Enabled = $false
$form.Controls.Add($runButton)

$retryButton = New-Object System.Windows.Forms.Button
$retryButton.Text = 'Retry'
$retryButton.Location = New-Object System.Drawing.Point(130, 385)
$retryButton.Size = New-Object System.Drawing.Size(100, 32)
$retryButton.Enabled = $false
$form.Controls.Add($retryButton)

$closeButton = New-Object System.Windows.Forms.Button
$closeButton.Text = 'Close'
$closeButton.Location = New-Object System.Drawing.Point(420, 385)
$closeButton.Size = New-Object System.Drawing.Size(100, 32)
$closeButton.Enabled = $false
$form.Controls.Add($closeButton)

function Write-Log {
    param([string]$Text)
    $log.AppendText($Text + "`r`n")
}

function Set-Progress {
    param([int]$Value)
    $progress.Value = [Math]::Min(100, [Math]::Max(0, $Value))
}

function Find-Python {
    foreach ($candidate in @('py', 'python')) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        try {
            $versionOutput = & $candidate -c "import sys; print(str(sys.version_info[0]) + '.' + str(sys.version_info[1]))" 2>$null
        } catch {
            continue
        }
        if ($LASTEXITCODE -ne 0 -or -not $versionOutput) { continue }
        $parts = $versionOutput.Trim().Split('.')
        if ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 9) {
            return $candidate
        }
    }
    return $null
}

function New-DesktopShortcut {
    param([string]$ProjectRoot)
    $desktop = [Environment]::GetFolderPath('Desktop')
    $shortcutPath = Join-Path $desktop 'Scholarly Translation.lnk'
    $wsh = New-Object -ComObject WScript.Shell
    $shortcut = $wsh.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $ProjectRoot 'Run Scholarly Translation.vbs'
    $shortcut.WorkingDirectory = $ProjectRoot
    $shortcut.IconLocation = 'shell32.dll,1'
    $shortcut.Description = 'Translate a PDF or EPUB to Hebrew (local UI)'
    $shortcut.Save()
    return $shortcutPath
}

function Run-Install {
    $log.Clear()
    Set-Progress 0
    $runButton.Enabled = $false
    $retryButton.Enabled = $false
    $closeButton.Enabled = $false
    try {
        Write-Log 'Looking for Python 3.9 or newer...'
        Set-Progress 5
        $python = Find-Python
        if (-not $python) {
            Write-Log 'Python 3.9+ was not found on PATH.'
            Write-Log 'Install it from https://www.python.org/downloads/ (check "Add python.exe to PATH"), then click Retry.'
            return
        }
        Write-Log "Found Python command: $python"
        Set-Progress 15

        $venvPath = Join-Path $projectRoot '.venv'
        $venvPython = Join-Path $venvPath 'Scripts\python.exe'
        if (-not (Test-Path $venvPython)) {
            Write-Log 'Creating an isolated virtual environment (.venv)...'
            & $python -m venv $venvPath
            if ($LASTEXITCODE -ne 0) { throw 'Creating .venv failed.' }
        } else {
            Write-Log '.venv already exists; reusing it.'
        }
        Set-Progress 35

        Write-Log 'Installing dependencies (pdfplumber, reportlab, Pillow)...'
        $requirements = Join-Path $projectRoot 'requirements.txt'
        $installOutput = & $venvPython -m pip install --disable-pip-version-check -r $requirements 2>&1
        $installOutput | ForEach-Object { Write-Log ([string]$_) }
        if ($LASTEXITCODE -ne 0) { throw 'Installing dependencies failed (see log above).' }
        Set-Progress 75

        Write-Log 'Verifying the installation...'
        $verify = & $venvPython -B -c "import pdfplumber, reportlab, PIL; print('ok')" 2>&1
        $verify | ForEach-Object { Write-Log ([string]$_) }
        if ($LASTEXITCODE -ne 0) { throw 'Verification failed (see log above).' }
        Set-Progress 90

        Write-Log 'Creating a desktop shortcut...'
        $shortcutPath = New-DesktopShortcut -ProjectRoot $projectRoot
        Write-Log "Shortcut created: $shortcutPath"
        Set-Progress 100

        Write-Log ''
        Write-Log 'Setup complete. Click "Run now" to open the translator, or use the desktop shortcut next time.'
        $runButton.Enabled = $true
    } catch {
        Write-Log ''
        Write-Log "Setup failed: $($_.Exception.Message)"
        $retryButton.Enabled = $true
    } finally {
        $closeButton.Enabled = $true
    }
}

$runButton.Add_Click({
    Start-Process -FilePath (Join-Path $projectRoot 'Run Scholarly Translation.vbs')
    $form.Close()
})
$retryButton.Add_Click({ Run-Install })
$closeButton.Add_Click({ $form.Close() })

$form.Add_Shown({
    $form.Activate()
    Run-Install
})
[void]$form.ShowDialog()
