<#
.SYNOPSIS
  Register (or refresh) the "TradingWorkbench Acct4 DailyCheck" scheduled task.

.DESCRIPTION
  Creates a Windows Task Scheduler job that runs scripts/acct4_daily_check_run.ps1
  every weekday at 15:10 local (America/Chicago) = 16:10 ET, after the 15:50 ET
  momentum-daily eval and just before the 16:35 ET box-side daily-report email.
  Runs in the current user's interactive context (inherits the SSH agent/keys and
  can pop Notepad on a non-PASS verdict) and catches a missed run if the machine
  was off (StartWhenAvailable). Re-running this script re-registers idempotently.

  Run once, from any shell, on the host:
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/register_acct4_daily_check_task.ps1
#>

$ErrorActionPreference = 'Stop'

$TaskName = 'TradingWorkbench Acct4 DailyCheck'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Runner   = Join-Path $RepoRoot 'scripts\acct4_daily_check_run.ps1'

if (-not (Test-Path $Runner)) { throw "runner not found at $Runner" }

$Action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`"" `
    -WorkingDirectory $RepoRoot

$Trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At 3:10pm

$Principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive
$Settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Principal $Principal -Settings $Settings `
    -Description 'Daily account-4 / momentum-daily (id=11) health check against the AWS box; pops the result if not PASS. Runbook: docs/runbook/account4_momentum_daily_daily_ops.md' `
    -Force | Out-Null

Write-Host "Registered '$TaskName': weekdays 15:10 local (16:10 ET)."
Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo | Format-List TaskName, NextRunTime, LastRunTime, LastTaskResult
