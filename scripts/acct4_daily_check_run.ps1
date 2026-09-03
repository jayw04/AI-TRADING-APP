<#
.SYNOPSIS
  Run the account-4 / momentum-daily daily health check against the AWS box.

.DESCRIPTION
  Scheduled-task runner (see register_acct4_daily_check_task.ps1). Pipes
  scripts/reports/acct4_daily_check.py into the backend container on the box
  (read-only), saves the dated result under logs\acct4_daily\, and appends a
  one-line summary to logs\acct4-daily-check.log. On any verdict other than
  PASS (or a failed run) it opens the result in Notepad so it gets seen.
  Runbook: docs/runbook/account4_momentum_daily_daily_ops.md
#>

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$CheckPy  = Join-Path $RepoRoot 'scripts\reports\acct4_daily_check.py'
$OutDir   = Join-Path $RepoRoot 'logs\acct4_daily'
$LogFile  = Join-Path $RepoRoot 'logs\acct4-daily-check.log'
$Stamp    = Get-Date -Format 'yyyy-MM-dd'
$OutFile  = Join-Path $OutDir "$Stamp.txt"

New-Item -ItemType Directory -Force $OutDir | Out-Null

$verdict = 'CRIT'
try {
    $output = Get-Content -Raw -Encoding UTF8 $CheckPy |
        ssh -o ClearAllForwardings=yes -o ConnectTimeout=30 -o BatchMode=yes workbench `
            'sudo docker exec -i workbench-backend python -' 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0 -or -not $output) {
        $output = "CHECK FAILED TO RUN (ssh exit $LASTEXITCODE)`n$output"
    } elseif ($output -match '=== VERDICT: (PASS|WARN|CRIT) ===') {
        $verdict = $Matches[1]
    } else {
        $output = "CHECK PRODUCED NO VERDICT LINE`n$output"
    }
} catch {
    $output = "CHECK FAILED TO RUN: $($_.Exception.Message)"
}

Set-Content -Path $OutFile -Value $output -Encoding UTF8
Add-Content -Path $LogFile -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') verdict=$verdict -> $OutFile" -Encoding UTF8

if ($verdict -ne 'PASS') {
    Copy-Item $OutFile (Join-Path $OutDir 'LATEST_ALERT.txt') -Force
    Start-Process notepad.exe $OutFile
}
