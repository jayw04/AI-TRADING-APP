<#
.SYNOPSIS
  Headless durability backstop for the PORT-001 §4 first-rebalance verification.

.DESCRIPTION
  Runs the READ-ONLY check (apps/backend/scripts/port001_first_rebalance_check.py) against the
  live backend by piping it into the container over stdin (so it does NOT depend on the script
  being baked into the image), captures the Markdown report to a timestamped file under
  docs/implementation/evidence/port_001/, and prints the verdict (PASS/WARN/FAIL).

  This is the backstop for the in-session Claude post-rebalance task: it captures the evidence
  even if no Claude session is running on Monday. It NEVER places orders or mutates anything.

  Run manually any time, or via the registered one-shot task (see
  scripts/register_port001_first_rebalance_task.ps1).
#>

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$CheckPy = Join-Path $RepoRoot 'apps\backend\scripts\port001_first_rebalance_check.py'
if (-not (Test-Path $CheckPy)) { throw "check script not found at $CheckPy" }

$OutDir = Join-Path $RepoRoot 'docs\implementation\evidence\port_001'
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$Stamp  = (Get-Date).ToString('yyyy-MM-dd')
$Report = Join-Path $OutDir "first_rebalance_check_$Stamp.md"

# Pipe the check into the running backend container (no image rebuild needed).
# NB: PowerShell variables are case-insensitive — keep the content var name distinct from $Report.
$reportText = Get-Content $CheckPy -Raw | docker compose exec -T backend python - 2>&1 | Out-String

[System.IO.File]::WriteAllText($Report, $reportText, [System.Text.UTF8Encoding]::new($false))
Write-Host "PORT-001 first-rebalance report -> $Report"
Write-Host ('-' * 60)
Write-Host $reportText

# Surface the verdict as the task's last line / exit signal.
if ($reportText -match '## Verdict:\s*(\w+)') {
    $verdict = $Matches[1]
    Write-Host "VERDICT: $verdict"
    if ($verdict -eq 'FAIL') { exit 1 }
}
exit 0
