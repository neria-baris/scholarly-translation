$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$candidates = @(
    (Join-Path $projectRoot '.venv\Scripts\python.exe'),
    'python',
    'py',
    (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
)

foreach ($candidate in $candidates) {
    if (-not (Get-Command $candidate -ErrorAction SilentlyContinue)) { continue }
    & $candidate -B -c 'import pdfplumber' 2>$null
    if ($LASTEXITCODE -eq 0) {
        Push-Location $projectRoot
        try {
            & $candidate -B -m scholarly_translation.web_ui
            exit $LASTEXITCODE
        } finally {
            Pop-Location
        }
    }
}

Write-Error 'Python with pdfplumber was not found. Install Python 3.9+ and run: py -m pip install -r requirements.txt'
