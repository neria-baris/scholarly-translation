$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot

# Import names that must load after installing requirements.txt
# (keep in sync with requirements.txt; Pillow imports as PIL).
$verifyModules = @('pdfplumber', 'reportlab', 'PIL', 'tiktoken', 'openai', 'anthropic')

# Pinned official per-user Python installer used only when Python 3.10+ is
# missing and winget is unavailable or did not succeed.
$pythonOrgVersion = '3.12.10'
$pythonOrgInstallerUrl = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe'
$wingetPythonId = 'Python.Python.3.12'

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
$subLabel.Text = 'Installs Python 3.12 for this user if needed, then dependencies into a local .venv, and creates a desktop shortcut. No admin rights required.'
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
    [System.Windows.Forms.Application]::DoEvents()
}

function Set-Progress {
    param([int]$Value)
    $progress.Value = [Math]::Min(100, [Math]::Max(0, $Value))
    [System.Windows.Forms.Application]::DoEvents()
}

function ConvertTo-ProcessArgument {
    param([string]$Value)
    if ($Value -ne '' -and $Value -notmatch '[\s"]') { return $Value }
    $escaped = $Value -replace '(\\*)"', '$1$1\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    return '"' + $escaped + '"'
}

function Receive-ProcessLines {
    param([string[]]$SourceIds)
    $events = @(Get-Event | Where-Object { $SourceIds -contains $_.SourceIdentifier } | Sort-Object EventIdentifier)
    foreach ($ev in $events) {
        $line = $ev.SourceEventArgs.Data
        if ($null -ne $line -and ([string]$line).Trim() -ne '') { Write-Log ([string]$line) }
        Remove-Event -EventIdentifier $ev.EventIdentifier
    }
}

# Runs a process without a console window, streams its output into the log
# and keeps the window responsive (DoEvents) until it exits. Returns the exit code.
function Invoke-ProcessWithUi {
    param([string]$FilePath, [string[]]$Arguments = @())
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = (($Arguments | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' ')
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    $id = [guid]::NewGuid().ToString('N')
    $ids = @("st-out-$id", "st-err-$id")
    Register-ObjectEvent -InputObject $proc -EventName OutputDataReceived -SourceIdentifier $ids[0] | Out-Null
    Register-ObjectEvent -InputObject $proc -EventName ErrorDataReceived -SourceIdentifier $ids[1] | Out-Null
    try {
        [void]$proc.Start()
        $proc.BeginOutputReadLine()
        $proc.BeginErrorReadLine()
        while (-not $proc.WaitForExit(100)) {
            Receive-ProcessLines $ids
            [System.Windows.Forms.Application]::DoEvents()
        }
        $proc.WaitForExit()
        Receive-ProcessLines $ids
        return $proc.ExitCode
    } finally {
        foreach ($sourceId in $ids) { Unregister-Event -SourceIdentifier $sourceId -ErrorAction SilentlyContinue }
        $proc.Dispose()
    }
}

# Refresh PATH for this session from the registry (User + Machine), so a
# Python installed a moment ago is visible without restarting the window.
function Update-SessionPath {
    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = (@($machinePath, $userPath) | Where-Object { $_ }) -join ';'
}

# Probes one candidate (command name or full path, plus optional leading
# arguments such as '-3.12'). Returns the resolved python.exe path when it is
# Python 3.10 or newer, otherwise $null.
function Test-PythonCandidate {
    param([string]$Exe, [string[]]$PrefixArgs = @())
    if ([System.IO.Path]::IsPathRooted($Exe)) {
        if (-not (Test-Path -LiteralPath $Exe)) { return $null }
    } elseif (-not (Get-Command $Exe -CommandType Application -ErrorAction SilentlyContinue)) {
        return $null
    }
    $probe = 'import sys; print(str(sys.version_info[0]) + chr(46) + str(sys.version_info[1])); print(sys.executable)'
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $Exe @PrefixArgs -c $probe 2>$null
        $exitCode = $LASTEXITCODE
    } catch {
        return $null
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($exitCode -ne 0 -or -not $output) { return $null }
    $lines = @($output | ForEach-Object { ([string]$_).Trim() } | Where-Object { $_ })
    if ($lines.Count -lt 2) { return $null }
    $parts = $lines[0].Split('.')
    $major = 0; $minor = 0
    if (-not [int]::TryParse($parts[0], [ref]$major)) { return $null }
    if ($parts.Count -lt 2 -or -not [int]::TryParse($parts[1], [ref]$minor)) { return $null }
    if ($major -ne 3 -or $minor -lt 10) { return $null }
    $executable = $lines[1]
    if (-not (Test-Path -LiteralPath $executable)) { return $null }
    return $executable
}

function Get-PerUserPythonPaths {
    $paths = @()
    foreach ($root in @((Join-Path $env:LOCALAPPDATA 'Programs\Python'), $env:ProgramFiles)) {
        if (-not $root -or -not (Test-Path -LiteralPath $root)) { continue }
        # Matches Python31*, Python310..Python313 etc.; newest first.
        $dirs = Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^Python3\d+$' } |
            Sort-Object { [int]($_.Name -replace '\D', '') } -Descending
        foreach ($dir in $dirs) {
            $exe = Join-Path $dir.FullName 'python.exe'
            if (Test-Path -LiteralPath $exe) { $paths += $exe }
        }
    }
    return $paths
}

# Returns a full path to a python.exe that is 3.10+, or $null. The py launcher
# is asked for explicit versions first because a default 'python' or 'py' may
# be an older interpreter (e.g. 3.9).
function Find-Python {
    $candidates = @()
    foreach ($version in @('3.13', '3.12', '3.11', '3.10')) {
        $candidates += , @('py', @("-$version"))
    }
    foreach ($path in (Get-PerUserPythonPaths)) {
        $candidates += , @($path, @())
    }
    $candidates += , @('python', @())
    $candidates += , @('python3', @())
    $candidates += , @('py', @())
    $candidates += , @((Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'), @())

    foreach ($candidate in $candidates) {
        [System.Windows.Forms.Application]::DoEvents()
        $resolved = Test-PythonCandidate -Exe $candidate[0] -PrefixArgs $candidate[1]
        if ($resolved) { return $resolved }
    }
    return $null
}

function Install-PythonWithWinget {
    $winget = Get-Command 'winget' -CommandType Application -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Log 'winget is not available on this computer.'
        return
    }
    Write-Log "Installing Python ($wingetPythonId) for this user with winget. This can take a few minutes..."
    $wingetArgs = @('install', '-e', '--id', $wingetPythonId, '--scope', 'user', '--silent',
        '--accept-package-agreements', '--accept-source-agreements')
    try {
        $code = Invoke-ProcessWithUi -FilePath $winget.Source -Arguments $wingetArgs
        Write-Log "winget finished with exit code $code."
    } catch {
        Write-Log "winget could not run: $($_.Exception.Message)"
    }
}

function Install-PythonFromPythonOrg {
    $url = $pythonOrgInstallerUrl
    if (-not $url.StartsWith('https://www.python.org/')) { throw 'Refusing a non-HTTPS Python download URL.' }
    $installer = Join-Path $env:TEMP "python-$pythonOrgVersion-amd64.exe"
    Write-Log "Downloading the official Python $pythonOrgVersion installer from python.org..."
    Write-Log $url
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $client = New-Object System.Net.WebClient
    try {
        $task = $client.DownloadFileTaskAsync($url, $installer)
        $lastReport = [DateTime]::UtcNow
        while (-not $task.IsCompleted) {
            Start-Sleep -Milliseconds 100
            [System.Windows.Forms.Application]::DoEvents()
            if (([DateTime]::UtcNow - $lastReport).TotalSeconds -ge 3 -and (Test-Path -LiteralPath $installer)) {
                $mb = [Math]::Round((Get-Item -LiteralPath $installer).Length / 1MB, 1)
                Write-Log "  downloaded $mb MB..."
                $lastReport = [DateTime]::UtcNow
            }
        }
        if ($task.IsFaulted -or $task.IsCanceled) {
            $reason = if ($task.Exception) { $task.Exception.GetBaseException().Message } else { 'cancelled' }
            throw "Downloading Python failed: $reason"
        }
    } finally {
        $client.Dispose()
    }

    $signature = Get-AuthenticodeSignature -FilePath $installer
    if ($signature.Status -ne 'Valid' -or -not $signature.SignerCertificate -or
        $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
        Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
        throw 'The downloaded Python installer is not validly signed by the Python Software Foundation.'
    }

    Write-Log 'Running the Python installer quietly for this user (no admin rights). This can take a few minutes...'
    $installArgs = @('/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_launcher=1',
        'InstallLauncherAllUsers=0', 'Include_test=0')
    try {
        $code = Invoke-ProcessWithUi -FilePath $installer -Arguments $installArgs
        Write-Log "Python installer finished with exit code $code."
    } finally {
        Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
    }
}

# Installs Python per-user (winget first, python.org fallback), refreshes PATH
# and re-detects. Returns a python.exe path or $null.
function Install-PythonForUser {
    Install-PythonWithWinget
    Update-SessionPath
    $python = Find-Python
    if ($python) { return $python }

    try {
        Install-PythonFromPythonOrg
    } catch {
        Write-Log $_.Exception.Message
    }
    Update-SessionPath
    return (Find-Python)
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

function Test-VenvHealthy {
    param([string]$VenvPython)
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $VenvPython -B -c 'import sys; assert sys.version_info >= (3, 10)' 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Run-Install {
    $log.Clear()
    Set-Progress 0
    $runButton.Enabled = $false
    $retryButton.Enabled = $false
    $closeButton.Enabled = $false
    try {
        Write-Log 'Looking for Python 3.10 or newer...'
        Set-Progress 5
        $python = Find-Python
        if (-not $python) {
            Write-Log 'Python 3.10+ was not found. Installing Python for this user automatically (internet connection required)...'
            Set-Progress 8
            $python = Install-PythonForUser
            if (-not $python) {
                throw ('Python 3.10+ could not be installed automatically. Check the internet connection and click Retry, ' +
                    'or install Python from https://www.python.org/downloads/ and click Retry.')
            }
        }
        Write-Log "Using Python: $python"
        Set-Progress 20

        $venvPath = Join-Path $projectRoot '.venv'
        $venvPython = Join-Path $venvPath 'Scripts\python.exe'
        if ((Test-Path $venvPython) -and -not (Test-VenvHealthy $venvPython)) {
            Write-Log 'Existing .venv is unusable; preserving it and using outputs/tooling/runtime-venv.'
            $venvPath = Join-Path $projectRoot 'outputs\tooling\runtime-venv'
            $venvPython = Join-Path $venvPath 'Scripts\python.exe'
            if ((Test-Path $venvPython) -and -not (Test-VenvHealthy $venvPython)) {
                throw 'Both .venv and outputs/tooling/runtime-venv are unusable. Delete outputs/tooling/runtime-venv and click Retry.'
            }
        }
        if (-not (Test-Path $venvPython)) {
            Write-Log 'Creating a local isolated virtual environment...'
            $code = Invoke-ProcessWithUi -FilePath $python -Arguments @('-m', 'venv', $venvPath)
            if ($code -ne 0) { throw 'Creating the virtual environment failed.' }
        } else {
            Write-Log 'Reusing the selected local virtual environment.'
        }
        Set-Progress 35

        Write-Log 'Upgrading pip in the virtual environment...'
        $code = Invoke-ProcessWithUi -FilePath $venvPython -Arguments @('-m', 'pip', 'install', '--disable-pip-version-check', '--upgrade', 'pip')
        if ($code -ne 0) { Write-Log 'Warning: upgrading pip failed; continuing with the existing pip.' }
        Set-Progress 45

        Write-Log 'Installing document, tokenizer and provider SDK dependencies...'
        $requirements = Join-Path $projectRoot 'requirements.txt'
        $code = Invoke-ProcessWithUi -FilePath $venvPython -Arguments @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', $requirements)
        if ($code -ne 0) { throw 'Installing dependencies failed (see log above).' }
        Set-Progress 80

        Write-Log 'Verifying the installation...'
        $verifyCode = "import sys; assert sys.version_info >= (3, 10); import $($verifyModules -join ', '); print('ok')"
        $code = Invoke-ProcessWithUi -FilePath $venvPython -Arguments @('-B', '-c', $verifyCode)
        if ($code -ne 0) { throw 'Verification failed (see log above).' }
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
