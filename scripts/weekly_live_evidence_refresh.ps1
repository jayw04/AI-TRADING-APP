<#
.SYNOPSIS
  Unattended weekly P12.5 live paper-trading evidence refresh.

.DESCRIPTION
  Regenerates the live-evidence report from the live workbench SQLite DB,
  archives a dated copy, and opens a docs-only PR. Intended for Windows Task
  Scheduler (weekly, Saturday 08:00 America/Chicago). The DB read is read-only;
  the only writes are the regenerated evidence files + git/gh.

  This is the LOCAL durable mechanism for the weekly refresh: a cloud /schedule
  routine cannot do it because data/workbench.sqlite is gitignored and only
  exists on this machine (the live Docker-mounted paper book).

  Prereqs on the host:
    - git + gh CLI, gh authenticated (`gh auth status`)
    - backend venv at apps/backend/.venv
    - live DB at data/workbench.sqlite
  The Docker stack does NOT need to be running (the script reads the SQLite file
  directly); the equity curve only accrues while the backend's daily snapshot
  job runs. Idempotent: re-running on the same day is a no-op (branch exists);
  a run with no DB changes abandons its branch and opens no PR.

  Register with: scripts/register_weekly_live_evidence_task.ps1
#>

$ErrorActionPreference = 'Stop'
# Native non-zero EXIT codes should not auto-throw (git/gh report status via
# $LASTEXITCODE, which we check explicitly). PS 7.4+ only; no-op on 5.1.
if ($PSVersionTable.PSVersion.Major -ge 7) { $PSNativeCommandUseErrorActionPreference = $false }

# Repo root = parent of this script's dir.
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$LogDir = Join-Path $RepoRoot 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir 'live-evidence-refresh.log'
function Log($m) {
    $line = '[{0}] {1}' -f (Get-Date -Format 's'), $m
    Add-Content -Path $Log -Value $line
    Write-Host $line
}
# Pipe native command output through the log.
function LogPipe { process { Log $_ } }

Log '=== weekly live-evidence refresh ==='

$Py        = Join-Path $RepoRoot 'apps\backend\.venv\Scripts\python.exe'
$Db        = Join-Path $RepoRoot 'data\workbench.sqlite'
$ReportDir = 'docs/implementation/evidence/p12_5_live'
$Date      = Get-Date -Format 'yyyy-MM-dd'
$Branch    = "docs/p12-5-live-evidence-$Date"

if (-not (Test-Path $Py)) { Log "ERROR: backend venv python not found at $Py"; exit 1 }
if (-not (Test-Path $Db)) { Log "ERROR: live DB not found at $Db"; exit 1 }

# Already refreshed today? (branch exists locally or on origin) -> nothing to do.
if ((git branch --list $Branch) -or (git ls-remote --heads origin $Branch)) {
    Log "branch $Branch already exists - already refreshed today; nothing to do"
    exit 0
}

# Start from a fresh main; best-effort fast-forward (never fatal).
git checkout main 2>&1 | LogPipe
git pull --ff-only origin main 2>&1 | LogPipe
if ($LASTEXITCODE -ne 0) { Log 'warn: git pull --ff-only failed; continuing on local main' }

git checkout -b $Branch 2>&1 | LogPipe
if ($LASTEXITCODE -ne 0) { Log "ERROR: could not create branch $Branch"; exit 1 }

# Regenerate the reports for EVERY live PAPER book (per-strategy live_evidence_<id>.{json,md}
# plus the canonical live_evidence.{json,md} for id=2) so new books (SEC-001, LOW-001) accrue.
& $Py 'apps/backend/scripts/live_evidence.py' --db $Db --all-paper --report-dir $ReportDir 2>&1 | LogPipe
if ($LASTEXITCODE -ne 0) {
    Log "ERROR: live_evidence.py exited $LASTEXITCODE"
    git checkout main 2>&1 | LogPipe; git branch -D $Branch 2>&1 | LogPipe
    exit 1
}

# Per-account Production Confidence Score + Operational KPI scorecard (platform canonical +
# per-book confidence_score_<id>/ops_kpis_<id>) so the weekly PR carries the full per-account set.
& $Py 'apps/backend/scripts/confidence_score.py' --db $Db --all-paper --report-dir $ReportDir 2>&1 | LogPipe
if ($LASTEXITCODE -ne 0) { Log "ERROR: confidence_score.py exited $LASTEXITCODE"; git checkout main 2>&1 | LogPipe; git branch -D $Branch 2>&1 | LogPipe; exit 1 }
& $Py 'apps/backend/scripts/ops_kpis.py' --db $Db --all-paper --report-dir $ReportDir 2>&1 | LogPipe
if ($LASTEXITCODE -ne 0) { Log "ERROR: ops_kpis.py exited $LASTEXITCODE"; git checkout main 2>&1 | LogPipe; git branch -D $Branch 2>&1 | LogPipe; exit 1 }

# Archive a dated copy of all generated reports (matches the manual convention archive/<date>/).
$ArchiveDir = Join-Path $ReportDir "archive/$Date"
New-Item -ItemType Directory -Force -Path $ArchiveDir | Out-Null
foreach ($pat in 'live_evidence*', 'confidence_score*', 'ops_kpis*') {
    Copy-Item (Join-Path $ReportDir "$pat.json") $ArchiveDir -Force -ErrorAction SilentlyContinue
    Copy-Item (Join-Path $ReportDir "$pat.md")   $ArchiveDir -Force -ErrorAction SilentlyContinue
}

git add "$ReportDir/live_evidence*.json" "$ReportDir/live_evidence*.md" `
        "$ReportDir/confidence_score*.json" "$ReportDir/confidence_score*.md" `
        "$ReportDir/ops_kpis*.json" "$ReportDir/ops_kpis*.md" "$ReportDir/archive/$Date" 2>&1 | LogPipe

# No changes vs the committed report (DB unchanged since last run)? Abandon.
git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Log 'no changes vs committed report - abandoning branch, no PR'
    git checkout main 2>&1 | LogPipe; git branch -D $Branch 2>&1 | LogPipe
    exit 0
}

$Msg = @"
docs(p12.5): refresh live paper-trading evidence ($Date)

Automated weekly live_evidence.py refresh (Windows Task Scheduler).
Read-only against data/workbench.sqlite; dated copy archived under
archive/$Date/.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
"@
git commit -m $Msg 2>&1 | LogPipe
if ($LASTEXITCODE -ne 0) { Log 'ERROR: git commit failed'; exit 1 }

git push -u origin $Branch 2>&1 | LogPipe
if ($LASTEXITCODE -ne 0) { Log 'ERROR: git push failed'; exit 1 }

$Body = @"
Automated weekly refresh of the P12.5 live paper-trading evidence report (Windows Task Scheduler, Sat 08:00 CT). Read-only against the live ``data/workbench.sqlite``; docs-only.

Regenerated per-account ``live_evidence_<id>``, ``confidence_score_<id>``, ``ops_kpis_<id>`` (+ the platform canonicals) + a dated archive under ``archive/$Date/`` — each live book now carries its own evidence trail (return / drawdown / Sharpe / turnover / cost / risk events) alongside the platform-wide rollup.

Generated by ``scripts/weekly_live_evidence_refresh.ps1``.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
"@
gh pr create --base main --head $Branch --title "docs(p12.5): refresh live paper-trading evidence ($Date)" --body $Body 2>&1 | LogPipe
if ($LASTEXITCODE -ne 0) { Log 'ERROR: gh pr create failed (branch pushed; open the PR manually)'; exit 1 }

git checkout main 2>&1 | LogPipe  # leave the repo on main
Log "done - PR opened for $Branch"
