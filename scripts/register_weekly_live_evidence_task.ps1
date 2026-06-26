<#
.SYNOPSIS
  Register (or refresh) the "TradingWorkbench LiveEvidence Weekly" scheduled task.

.DESCRIPTION
  Creates a Windows Task Scheduler job that runs scripts/weekly_live_evidence_refresh.ps1
  every Saturday at 08:00 local time (America/Chicago). Runs in the current user's
  interactive context (so it inherits gh auth + git creds) and catches a missed run
  if the machine was off at 08:00 (StartWhenAvailable). Re-running this script
  re-registers the task idempotently.

  Run once, from any shell, on the host:
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/register_weekly_live_evidence_task.ps1
#>

$ErrorActionPreference = 'Stop'

$TaskName = 'TradingWorkbench LiveEvidence Weekly'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Runner   = Join-Path $RepoRoot 'scripts\weekly_live_evidence_refresh.ps1'

if (-not (Test-Path $Runner)) { throw "runner not found at $Runner" }

$Action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`"" `
    -WorkingDirectory $RepoRoot

$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At 8:00am

# Interactive (logged-on user) so gh/git credentials are available; tolerate a
# missed start (machine off at 08:00) and don't kill a long push/PR.
$Principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive
$Settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Principal $Principal -Settings $Settings `
    -Description 'Weekly P12.5 live paper-trading evidence refresh -> docs-only PR (scripts/weekly_live_evidence_refresh.ps1).' `
    -Force | Out-Null

Write-Host "Registered '$TaskName': Saturdays 08:00 local."
Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo | Format-List TaskName, NextRunTime, LastRunTime, LastTaskResult
