$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$candidates = @(
    (Join-Path $projectRoot '.venv\Scripts\python.exe'),
    (Join-Path $projectRoot 'outputs\tooling\runtime-venv\Scripts\python.exe'),
    (Join-Path $projectRoot 'outputs\tooling\python39\python.exe'),
    'python',
    'py',
    (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
)

foreach ($candidate in $candidates) {
    if (-not (Get-Command $candidate -ErrorAction SilentlyContinue)) { continue }
    try { & $candidate -B -c 'import sys; assert sys.version_info >= (3, 10); import pdfplumber, reportlab, PIL, tiktoken, openai, anthropic' 2>$null } catch { continue }
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

Write-Error 'Python 3.10+ with project dependencies was not found. Run Install.bat, or install requirements.txt in a local virtual environment.'
