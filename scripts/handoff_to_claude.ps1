[CmdletBinding()]
param([switch]$ValidateOnly)

$ErrorActionPreference = 'Stop'
# Resolve from the helper's location, never the caller's current directory.
$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$requiredFiles = @('AGENTS.md', 'DEVELOPMENT_WORKFLOW.md', 'CLAUDE.md',
    'audit/current_state.md', 'audit/claude_integration_conductor.md')
foreach ($relativePath in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $repositoryRoot $relativePath) -PathType Leaf)) {
        throw "Required handoff file is missing: $relativePath"
    }
}
$claudeCommand = Get-Command claude -CommandType Application -ErrorAction Stop
Push-Location -LiteralPath $repositoryRoot
try {
    $gitRoot = & git rev-parse --show-toplevel
    if ($LASTEXITCODE -ne 0 -or
        [System.IO.Path]::GetFullPath($gitRoot.Trim()) -ne $repositoryRoot) {
        throw 'The helper must be inside the intended Git repository root.'
    }
    if ($ValidateOnly) {
        Write-Output "Validated handoff root and bootstrap files: $repositoryRoot"
        Write-Output "Claude executable: $($claudeCommand.Source)"
        return
    }
    $takeoverInstruction = @'
Assume the temporary conductor role for this repository under the user-authorized continuity exception. First read the existing instructions in their required order, especially AGENTS.md and DEVELOPMENT_WORKFLOW.md, then CLAUDE.md, audit/current_state.md and audit/claude_integration_conductor.md. Inspect Git status, remotes, branches, worktrees and the decorated all-branch graph yourself. A/B/C/E were already implemented; do not reimplement them. Git and audit/current_state.md are authoritative. Continue from the exact recorded next action. Preserve valid running delegated work instead of duplicating it. Perform verification, integration, audit and routine Git under the existing conductor policy. Use the same limits on parallel writers, worktrees, budgets, testing and Git. Ask the user only for genuine human decisions required by policy. Checkpoint before any availability limit and use the same mechanism to return responsibility to Sol.
'@
    # Claude's native background mode creates a separate resumable session and
    # leaves this terminal intact. It does not bypass permission checks.
    & $claudeCommand.Source --bg --model sonnet --permission-mode auto --name 'Translation integration conductor' $takeoverInstruction
    if ($LASTEXITCODE -ne 0) { throw "Claude handoff launcher exited with code $LASTEXITCODE" }
} finally {
    Pop-Location
}
