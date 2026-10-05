$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot

# Import names that must load (keep in sync with requirements.txt and
# install.ps1; Pillow imports as PIL).
$verifyModules = @('pdfplumber', 'reportlab', 'PIL', 'tiktoken', 'openai', 'anthropic')
$checkCode = "import sys; assert sys.version_info >= (3, 10); import $($verifyModules -join ', ')"

# Candidates as (command or full path, leading arguments). Project
# environments first, then explicit 3.10+ interpreters; bare 'python'/'py'
# (which may be an older default such as 3.9) come last.
$candidates = @()
$candidates += , @((Join-Path $projectRoot '.venv\Scripts\python.exe'), @())
$candidates += , @((Join-Path $projectRoot 'outputs\tooling\runtime-venv\Scripts\python.exe'), @())
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

foreach ($candidate in $candidates) {
    $exe = $candidate[0]
    $prefixArgs = @($candidate[1])
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    $ErrorActionPreference = 'Continue'
    try { & $exe @prefixArgs -B -c $checkCode 2>$null } catch { $ErrorActionPreference = 'Stop'; continue }
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = 'Stop'
    if ($ok) {
        Push-Location $projectRoot
        try {
            & $exe @prefixArgs -B -m scholarly_translation.web_ui
            exit $LASTEXITCODE
        } finally {
            Pop-Location
        }
    }
}

Write-Error 'Python 3.10+ with project dependencies was not found. Run Install.bat (it installs Python automatically if needed), or install requirements.txt in a local virtual environment.'
