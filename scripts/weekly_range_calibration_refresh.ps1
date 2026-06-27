<#
.SYNOPSIS
  Unattended weekly Range auto-select calibration refresh.

.DESCRIPTION
  Regenerates the Range-Score-band -> outcomes calibration report from the live
  workbench SQLite DB and opens a docs-only PR. Intended for Windows Task
  Scheduler (weekly, Friday 16:30 America/Chicago -- after the week's close, and
  deliberately NOT Saturday so it never races the live-evidence task's git ops).

  The DB read is read-only; the only writes are the regenerated report + git/gh.
  Mirrors scripts/weekly_live_evidence_refresh.ps1.

  EMPTY-WEEK SKIP: until the daily auto-select has actually selected names (first
  live fire Mon 2026-06-29), the report has no data. This script runs the report
  into a TEMP dir FIRST and, if there are zero selections, logs and exits doing
  NO git operations at all -- so it stays silent for the ~40 days before data
  accrues, then begins opening weekly PRs once there is something to report.

  Prereqs on the host: git + gh (authenticated), backend venv at
  apps/backend/.venv, live DB at data/workbench.sqlite. The Docker stack need
  not be running (reads the SQLite file directly).

  Register with: scripts/register_weekly_range_calibration_task.ps1
#>

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -ge 7) { $PSNativeCommandUseErrorActionPreference = $false }

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$LogDir = Join-Path $RepoRoot 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir 'range-calibration-refresh.log'
function Log($m) {
    $line = '[{0}] {1}' -f (Get-Date -Format 's'), $m
    Add-Content -Path $Log -Value $line
    Write-Host $line
}
function LogPipe { process { Log $_ } }

Log '=== weekly range-calibration refresh ==='

$Py        = Join-Path $RepoRoot 'apps\backend\.venv\Scripts\python.exe'
$Db        = Join-Path $RepoRoot 'data\workbench.sqlite'
$Script    = 'apps/backend/scripts/range_calibration_report.py'
$ReportDir = 'docs/implementation/evidence/range_calibration'
$Date      = Get-Date -Format 'yyyy-MM-dd'
$Branch    = "docs/range-calibration-$Date"

if (-not (Test-Path $Py)) { Log "ERROR: backend venv python not found at $Py"; exit 1 }
if (-not (Test-Path $Db)) { Log "ERROR: live DB not found at $Db"; exit 1 }

# --- DATA CHECK FIRST (read-only; no git): run into a temp dir and parse the count. ---
$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) "rangecal_check_$Date"
$out = & $Py $Script --db $Db --out $Tmp 2>&1
$out | LogPipe
$sel = -1
$joined = ($out | Out-String)   # collapse the line array so -match populates $Matches
if ($joined -match 'selections=(\d+)') { $sel = [int]$Matches[1] }
Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
if ($sel -le 0) {
    Log "no selections accrued yet (selections=$sel) - skipping; no git, no PR (the report populates once the daily auto-select fires)"
    exit 0
}

# --- DATA EXISTS: refresh on a docs branch off main and open a PR (mirrors live-evidence). ---
if ((git branch --list $Branch) -or (git ls-remote --heads origin $Branch)) {
    Log "branch $Branch already exists - already refreshed today; nothing to do"
    exit 0
}

git checkout main 2>&1 | LogPipe
git pull --ff-only origin main 2>&1 | LogPipe
if ($LASTEXITCODE -ne 0) { Log 'warn: git pull --ff-only failed; continuing on local main' }

git checkout -b $Branch 2>&1 | LogPipe
if ($LASTEXITCODE -ne 0) { Log "ERROR: could not create branch $Branch"; exit 1 }

& $Py $Script --db $Db --out $ReportDir 2>&1 | LogPipe
if ($LASTEXITCODE -ne 0) {
    Log "ERROR: range_calibration_report.py exited $LASTEXITCODE"
    git checkout main 2>&1 | LogPipe; git branch -D $Branch 2>&1 | LogPipe
    exit 1
}

# Archive a dated copy alongside the canonical report.
$ArchiveDir = Join-Path $ReportDir "archive/$Date"
New-Item -ItemType Directory -Force -Path $ArchiveDir | Out-Null
Copy-Item (Join-Path $ReportDir 'range_calibration.md') (Join-Path $ArchiveDir 'range_calibration.md') -Force

git add "$ReportDir/range_calibration.md" "$ReportDir/archive/$Date" 2>&1 | LogPipe

git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Log 'no changes vs committed report - abandoning branch, no PR'
    git checkout main 2>&1 | LogPipe; git branch -D $Branch 2>&1 | LogPipe
    exit 0
}

$Msg = @"
docs(range): refresh auto-select calibration report ($Date)

Automated weekly range_calibration_report.py refresh (Windows Task Scheduler).
Read-only against data/workbench.sqlite; score-band -> outcomes + Selection
Precision + Opportunity Conversion funnel. Dated copy under archive/$Date/.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
"@
git commit -m $Msg 2>&1 | LogPipe
if ($LASTEXITCODE -ne 0) { Log 'ERROR: git commit failed'; exit 1 }

git push -u origin $Branch 2>&1 | LogPipe
if ($LASTEXITCODE -ne 0) { Log 'ERROR: git push failed'; exit 1 }

$Body = @"
Automated weekly refresh of the Range auto-select **calibration report** (Windows Task Scheduler, Fri 16:30 CT). Read-only against the live ``data/workbench.sqlite``; docs-only.

Per Range-Score band: trades/exits, trigger rate, win rate, avg P&L, P&L Sharpe -- plus **Selection Precision** and the **Opportunity Conversion funnel** (v1.2 SS16). This is the rolling input the empirical ``auto_select_min_score`` threshold reads after >=40 trading days (ADR 0028).

Generated by ``scripts/weekly_range_calibration_refresh.ps1``.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
"@
gh pr create --base main --head $Branch --title "docs(range): refresh auto-select calibration report ($Date)" --body $Body 2>&1 | LogPipe
if ($LASTEXITCODE -ne 0) { Log 'ERROR: gh pr create failed (branch pushed; open the PR manually)'; exit 1 }

git checkout main 2>&1 | LogPipe
Log "done - PR opened for $Branch"
