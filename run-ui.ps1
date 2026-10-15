$ErrorActionPreference = 'Stop'
$scriptRoot = $PSScriptRoot
$projectRoot = $scriptRoot

# Installed layout (created by install.ps1): <install>\install.marker,
# <install>\app\<version>\ and <install>\app\current.txt. A development
# checkout has no marker and launches exactly as before.
$installMode = (Test-Path -LiteralPath (Join-Path $scriptRoot 'install.marker')) -and
    (Test-Path -LiteralPath (Join-Path $scriptRoot 'app\current.txt'))
$appDir = Join-Path $scriptRoot 'app'
$heartbeatFile = Join-Path $scriptRoot 'heartbeat.txt'   # keep in sync with app_paths.HEARTBEAT_NAME
$heartbeatTimeoutSeconds = 60

function Get-InstalledVersion {
    $text = (Get-Content -LiteralPath (Join-Path $appDir 'current.txt') -TotalCount 1 -ErrorAction Stop).Trim()
    if ($text -notmatch '^\d+(\.\d+){0,3}$') { throw "Invalid version in current.txt: $text" }
    return $text
}

if ($installMode) { $projectRoot = Join-Path $appDir (Get-InstalledVersion) }

# Import names that must load (keep in sync with requirements.txt and
# install.ps1; Pillow imports as PIL).
$verifyModules = @('pdfplumber', 'reportlab', 'PIL', 'tiktoken', 'openai', 'anthropic', 'cryptography')
$checkCode = "import sys; assert sys.version_info >= (3, 10); import $($verifyModules -join ', ')"

# Candidates as (command or full path, leading arguments). Project
# environments first, then explicit 3.10+ interpreters; bare 'python'/'py'
# (which may be an older default such as 3.9) come last. The environment
# lives in the install root (shared by all versions) when installed.
$envRoot = if ($installMode) { $scriptRoot } else { $projectRoot }
$candidates = @()
$candidates += , @((Join-Path $envRoot '.venv\Scripts\python.exe'), @())
$candidates += , @((Join-Path $envRoot 'outputs\tooling\runtime-venv\Scripts\python.exe'), @())
foreach ($version in @('3.13', '3.12', '3.11', '3.10')) {
    $candidates += , @('py', @("-$version"))
}
$perUserRoot = Join-Path $env:LOCALAPPDATA 'Programs\Python'
if (Test-Path -LiteralPath $perUserRoot) {
    Get-ChildItem -LiteralPath $perUserRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^Python3\d+$' -and [int]($_.Name -replace '\D', '') -ge 310 } |
        Sort-Object { [int]($_.Name -replace '\D', '') } -Descending |
        ForEach-Object { $script:candidates += , @((Join-Path $_.FullName 'python.exe'), @()) }
}
$candidates += , @('python', @())
$candidates += , @('py', @())
$candidates += , @((Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'), @())

# Runs one update-CLI command (scholarly_translation.update.updater) with the
# given interpreter and returns its single JSON line as an object, or $null.
function Invoke-UpdateCli {
    param([string]$Exe, [string[]]$PrefixArgs, [string]$Command, [string]$Reason = '', [string]$CodeVersion = '')
    $cliArgs = @('-B', '-m', 'scholarly_translation.update.updater', $Command, '--install-root', $scriptRoot)
    if ($Reason) { $cliArgs += @('--reason', $Reason) }
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    if (-not $CodeVersion) { $CodeVersion = Get-InstalledVersion }
    Push-Location (Join-Path $appDir $CodeVersion)
    try {
        $lines = & $Exe @PrefixArgs @cliArgs 2>$null
        $line = @($lines | Where-Object { ([string]$_).Trim().StartsWith('{') }) | Select-Object -Last 1
        if ($line) { return ($line | ConvertFrom-Json) }
        return $null
    } catch {
        return $null
    } finally {
        Pop-Location
        $ErrorActionPreference = $previous
    }
}

# Applies a staged (already downloaded and verified) update before launch.
# Returns $true when the version was switched (the next start is a trial run).
# Any failure leaves the old version active.
function Apply-StagedUpdate {
    param([string]$Exe, [string[]]$PrefixArgs)
    if (-not (Test-Path -LiteralPath (Join-Path $appDir 'staged.txt'))) { return $false }
    $info = Invoke-UpdateCli -Exe $Exe -PrefixArgs $PrefixArgs -Command 'prepare'
    if (-not $info -or $info.status -eq 'none') { return $false }
    if ($info.status -ne 'ready') {
        [void](Invoke-UpdateCli -Exe $Exe -PrefixArgs $PrefixArgs -Command 'reject' -Reason "verification failed: $($info.reason)")
        return $false
    }
    if ($info.requirements_changed) {
        # Only ever install into the project environment, never a system Python.
        if (-not ([string]$Exe).StartsWith($envRoot, [StringComparison]::OrdinalIgnoreCase)) {
            [void](Invoke-UpdateCli -Exe $Exe -PrefixArgs $PrefixArgs -Command 'reject' -Reason 'requirements changed but no project environment is available')
            return $false
        }
        Write-Host "Installing updated dependencies for version $($info.version)..."
        $previous = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            & $Exe @PrefixArgs -m pip install --disable-pip-version-check -r $info.requirements | Out-Host
            $pipOk = ($LASTEXITCODE -eq 0)
        } catch {
            $pipOk = $false
        } finally {
            $ErrorActionPreference = $previous
        }
        if (-not $pipOk) {
            [void](Invoke-UpdateCli -Exe $Exe -PrefixArgs $PrefixArgs -Command 'reject' -Reason 'pip install -r failed; staying on the old version')
            return $false
        }
    }
    $switched = Invoke-UpdateCli -Exe $Exe -PrefixArgs $PrefixArgs -Command 'switch'
    return [bool]($switched -and $switched.version)
}

# Starts the app and waits for it. When $Trial is set, a missing heartbeat
# within 60 seconds (or an early exit without one) rolls back to the previous
# version and records the reason in data\update.log, then starts that version.
function Start-App {
    param([string]$Exe, [string[]]$PrefixArgs, [bool]$Trial)
    $workDir = if ($installMode) { Join-Path $appDir (Get-InstalledVersion) } else { $projectRoot }
    if (-not $installMode) {
        Push-Location $workDir
        try {
            & $Exe @PrefixArgs -B -m scholarly_translation.ui.web_ui
            exit $LASTEXITCODE
        } finally {
            Pop-Location
        }
    }
    Remove-Item -LiteralPath $heartbeatFile -Force -ErrorAction SilentlyContinue
    $startedUtc = [DateTime]::UtcNow
    $proc = Start-Process -FilePath $Exe -ArgumentList (@($PrefixArgs) + @('-B', '-m', 'scholarly_translation.ui.web_ui')) `
        -WorkingDirectory $workDir -NoNewWindow -PassThru
    $null = $proc.Handle
    if ($Trial) {
        $alive = $false
        while (([DateTime]::UtcNow - $startedUtc).TotalSeconds -lt $heartbeatTimeoutSeconds) {
            if ((Test-Path -LiteralPath $heartbeatFile) -and ((Get-Item -LiteralPath $heartbeatFile).LastWriteTimeUtc -ge $startedUtc.AddSeconds(-2))) { $alive = $true; break }
            if ($proc.HasExited) { break }
            Start-Sleep -Milliseconds 500
        }
        if (-not $alive) {
            if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
            $reason = "no heartbeat within $heartbeatTimeoutSeconds seconds after update"
            # Run the rollback with the previous (known good) version's code: the
            # version that just failed to start may not be able to roll itself back.
            $previousVersion = ''
            $previousFile = Join-Path $appDir 'previous.txt'
            if (Test-Path -LiteralPath $previousFile) {
                $candidate = (Get-Content -LiteralPath $previousFile -TotalCount 1).Trim()
                if ($candidate -match '^\d+(\.\d+){0,3}$' -and (Test-Path -LiteralPath (Join-Path $appDir $candidate))) { $previousVersion = $candidate }
            }
            $result = Invoke-UpdateCli -Exe $Exe -PrefixArgs $PrefixArgs -Command 'rollback' -Reason $reason -CodeVersion $previousVersion
            if ($result -and $result.rolled_back) {
                Write-Host "The updated version did not start; returned to version $($result.to)."
                Start-App -Exe $Exe -PrefixArgs $PrefixArgs -Trial $false
                return
            }
            Write-Error 'The updated version did not start and no previous version is available.'
            exit 1
        }
    }
    $proc.WaitForExit()
    exit $proc.ExitCode
}

foreach ($candidate in $candidates) {
    $exe = $candidate[0]
    $prefixArgs = @($candidate[1])
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    $ErrorActionPreference = 'Continue'
    try { & $exe @prefixArgs -B -c $checkCode 2>$null } catch { $ErrorActionPreference = 'Stop'; continue }
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = 'Stop'
    if ($ok) {
        $trial = $false
        if ($installMode) {
            $trial = Apply-StagedUpdate -Exe $exe -PrefixArgs $prefixArgs
        }
        Start-App -Exe $exe -PrefixArgs $prefixArgs -Trial $trial
    }
}

Write-Error 'Python 3.10+ with project dependencies was not found. Run Install.bat (it installs Python automatically if needed), or install requirements.txt in a local virtual environment.'
