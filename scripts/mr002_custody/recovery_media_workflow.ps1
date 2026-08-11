<#
.SYNOPSIS
    MR-002 WP-A (A1-A4) — write and verify the external offline recovery copy.

.DESCRIPTION
    Automates the MECHANICAL parts of the owner procedure in
    docs/review/mr002/MR002_ExternalRecoveryCopy_Submission_v1.0.md sections 5-7:
    copying the bound evaluator archive to encrypted removable media and
    verifying it FROM that medium with the authoritative offline verifier
    (export_recovery_copy.py --verify).

    WHAT THIS DELIBERATELY DOES NOT DO
    ---------------------------------------------------------------------------
    It never accepts, generates, stores, echoes or logs a passphrase.

    Section 6 is explicit that the archive producer "must not handle encryption
    secrets", and section 7 forbids recording keys, passphrases or recovery
    phrases in any governance artifact. A passphrase passed as a parameter would
    also land in PowerShell history, the process list, and any session
    transcript. So volume creation and mounting stay INTERACTIVE — VeraCrypt
    prompts in its own dialog and this script drives everything around it.

    Every check FAILS CLOSED. A digest mismatch stops the run; it does not warn.

    SCOPE
    ---------------------------------------------------------------------------
    Governing invariant 10: no passing recovery verification satisfies custody
    Requirement 7 or authorizes execution. This closes a custody gap only.

.PARAMETER Step
    Preflight | A1 | A2 | A3 | A4. Run A4 BEFORE A3 — verification needs the
    volume still mounted.

.PARAMETER MountLetter
    Drive letter the encrypted volume is mounted to. Default V.

.PARAMETER StagingDir
    Machine-specific location of the built archive. Override per operator.

.PARAMETER OutDir
    Where the A4 verdict record is written. MUST be outside the repository —
    generated evidence does not belong in git (ADR 0050). Guarded below.

.EXAMPLE
    .\recovery_media_workflow.ps1 -Step Preflight
    .\recovery_media_workflow.ps1 -Step A1
    .\recovery_media_workflow.ps1 -Step A2 -MountLetter V
    .\recovery_media_workflow.ps1 -Step A4 -MountLetter V
    .\recovery_media_workflow.ps1 -Step A3 -MountLetter V

.NOTES
    VeraCrypt must run ELEVATED to enumerate raw devices; an unelevated instance
    shows an empty "Select Device..." picker. -Step A1 launches it with RunAs.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('Preflight', 'A1', 'A2', 'A3', 'A4')]
    [string]$Step,

    [ValidatePattern('^[D-Z]$')]
    [string]$MountLetter = 'V',

    # Repo root derived from this script's location: <repo>/scripts/mr002_custody/
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,

    [string]$StagingDir = 'C:\LLM-RAG-APP\mr002_recovery_staging',

    [string]$OutDir,

    [int]$UsbDiskNumber = 1
)

$ErrorActionPreference = 'Stop'

# --- Governing identities. Bound by P5; never edit these to make a run pass. ---
$OUTER_SHA = 'c3cf3b9e3cb1f5a5ce94f79ede72163ab1389803fbd3f0dfc91d8744604f9f8a'
$INNER_SHA = '60b15568aa5960ee04cf10b8c9b006d2ee702aa815a17384beffc979ed4554c9'
$TAR_BYTES = 44410880
$TAR_NAME  = 'mr002-evaluator-p5-recovery.tar'
$SIDECAR   = 'MR002_ExternalRecoveryCopy_v1.0.json'

$VeraCrypt  = 'C:\Program Files\VeraCrypt\VeraCrypt.exe'
$Python     = Join-Path $RepoRoot 'apps\backend\.venv\Scripts\python.exe'
$Verifier   = Join-Path $PSScriptRoot 'export_recovery_copy.py'
$SourceTar  = Join-Path $StagingDir $TAR_NAME
$DevicePath = "\Device\Harddisk$UsbDiskNumber\Partition1"

if (-not $OutDir) { $OutDir = Split-Path $RepoRoot -Parent }

function Say  { param($m) Write-Host $m }
function Ok   { param($m) Write-Host "  [OK]   $m" -ForegroundColor Green }
function Warn { param($m) Write-Host "  [WARN] $m" -ForegroundColor Yellow }
function Die  { param($m) Write-Host "  [STOP] $m" -ForegroundColor Red; exit 1 }

function Get-Sha256Lower { param([string]$Path) (Get-FileHash -Path $Path -Algorithm SHA256).Hash.ToLower() }

function Assert-OutDirOutsideRepo {
    $o = [IO.Path]::GetFullPath($OutDir).TrimEnd('\')
    $r = [IO.Path]::GetFullPath($RepoRoot).TrimEnd('\')
    if ($o.StartsWith($r, [StringComparison]::OrdinalIgnoreCase)) {
        Die "OutDir '$o' is inside the repository. Generated evidence must not land in git (ADR 0050)."
    }
}

function Assert-SourceArchive {
    if (-not (Test-Path $SourceTar)) { Die "source archive not found: $SourceTar" }
    $len = (Get-Item $SourceTar).Length
    if ($len -ne $TAR_BYTES) { Die "source size $len != expected $TAR_BYTES" }
    $h = Get-Sha256Lower $SourceTar
    if ($h -ne $OUTER_SHA) { Die "source digest mismatch`n    got      $h`n    expected $OUTER_SHA" }
    Ok "source archive intact ($TAR_BYTES bytes, $($OUTER_SHA.Substring(0,12))...)"
}

function Get-MountPath {
    $p = "${MountLetter}:"
    if (-not (Test-Path $p)) {
        Die "$p is not mounted. Mount the encrypted volume in the VeraCrypt GUI:`n" +
            "    select the $MountLetter row -> Select Device... -> $DevicePath -> Mount`n" +
            "  PRF Autodetection, PIM blank, TrueCrypt Mode unchecked.`n" +
            "  (Do not use the CLI /q form: it quits before you can type the passphrase.)"
    }
    return $p
}

switch ($Step) {

'Preflight' {
    Say "`n=== MR-002 WP-A preflight ===`n"
    Assert-OutDirOutsideRepo
    Assert-SourceArchive
    if (-not (Test-Path $VeraCrypt)) { Die "VeraCrypt not found at $VeraCrypt" }
    if (-not (Test-Path $Python))    { Die "python not found at $Python" }
    if (-not (Test-Path $Verifier))  { Die "verifier not found at $Verifier" }
    Ok "VeraCrypt, python and the offline verifier are present"

    $disk = Get-Disk -Number $UsbDiskNumber -ErrorAction SilentlyContinue
    if (-not $disk)              { Die "disk $UsbDiskNumber not found" }
    if ($disk.IsSystem)          { Die "disk $UsbDiskNumber is the SYSTEM disk - refusing" }
    if ($disk.IsBoot)            { Die "disk $UsbDiskNumber is the BOOT disk - refusing" }
    if ($disk.BusType -ne 'USB') { Die "disk $UsbDiskNumber bus is $($disk.BusType), expected USB" }
    Ok "target disk $UsbDiskNumber = $($disk.FriendlyName), USB, not system/boot"

    $part = Get-Partition -DiskNumber $UsbDiskNumber -ErrorAction SilentlyContinue |
            Where-Object { $_.DriveLetter }
    if ($part) {
        $letter = "$($part.DriveLetter):"
        # An already-encrypted VeraCrypt device is unreadable to Windows and
        # Get-ChildItem throws rather than returning empty, so probe readability
        # first. Unreadable is the SAFE case: no plaintext data to destroy.
        $vol = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$letter'" -ErrorAction SilentlyContinue
        if (-not ($vol -and $vol.FileSystem)) {
            Ok "$letter has no readable filesystem (already encrypted, or raw) - nothing in the clear to lose"
        }
        else {
            $items = @()
            try {
                $items = @(Get-ChildItem $letter -Force -Recurse -ErrorAction SilentlyContinue |
                           Where-Object { $_.FullName -notlike "*System Volume Information*" })
            } catch { Warn "could not enumerate $letter - treating as unreadable" }
            if ($items.Count -gt 0) {
                Warn "$letter holds $($items.Count) user item(s) - VOLUME CREATION WILL DESTROY THEM:"
                $items | Select-Object -First 10 FullName | ForEach-Object { Write-Host "         $($_.FullName)" }
                Die "refusing to continue while the medium holds data. Move it, then re-run."
            }
            Ok "$letter holds no user data (System Volume Information only)"
        }
    }
    Say "`nPreflight PASSED. Next: -Step A1`n"
}

'A1' {
    Say "`n=== A1 - create the encrypted volume (INTERACTIVE) ===`n"
    Assert-SourceArchive
    Say @"
  You set the passphrase, not this script.

  VeraCrypt opens ELEVATED (raw-device enumeration needs admin; an unelevated
  instance shows an EMPTY 'Select Device...' picker). In the wizard:

    1. Create Volume
    2. 'Encrypt a non-system partition/drive'
    3. Standard VeraCrypt volume
    4. Select Device...  ->  Harddisk$UsbDiskNumber Partition1
       ** NOT Harddisk0 - that is the system disk, listed directly above **
    5. 'Create encrypted volume and format it'
    6. Encryption AES / KDF SHA-512
    7. Passphrase -> your password manager ONLY. Never in the repo, a commit
       message, or the section 7 record.
    8. Filesystem exFAT, TICK 'Quick Format'
    9. Format, then Exit

  Then mount in the GUI: select the $MountLetter row -> Select Device... -> Mount
  (PRF Autodetection, PIM blank, TrueCrypt Mode unchecked)

  Then: -Step A2 -MountLetter $MountLetter
"@
    Warn "Do NOT use gpg / 7-Zip / age on the .tar - file-level encryption changes the"
    Warn "bytes and the outer digest $($OUTER_SHA.Substring(0,12))... will no longer verify."
    Start-Process -FilePath $VeraCrypt -Verb RunAs | Out-Null
    Ok "VeraCrypt launched elevated"
}

'A2' {
    Say "`n=== A2 - write the archive to the encrypted medium ===`n"
    Assert-SourceArchive
    $mnt = Get-MountPath
    Ok "$mnt is mounted"

    Copy-Item $SourceTar -Destination $mnt -Force
    $sc = Join-Path $StagingDir $SIDECAR
    if (Test-Path $sc) { Copy-Item $sc -Destination $mnt -Force; Ok "sidecar $SIDECAR copied" }

    $dest = Join-Path $mnt $TAR_NAME
    $len = (Get-Item $dest).Length
    if ($len -ne $TAR_BYTES) { Die "copied size $len != expected $TAR_BYTES - recopy" }
    $h = Get-Sha256Lower $dest
    if ($h -ne $OUTER_SHA) { Die "copied digest MISMATCH`n    got      $h`n    expected $OUTER_SHA`n  Recopy; do not proceed." }
    Ok "copy is byte-identical ($TAR_BYTES bytes)"
    Ok "outer digest verified: $OUTER_SHA"
    Say "`nNext: -Step A4 (verify FROM the medium), THEN -Step A3 (dismount)`n"
}

'A4' {
    Say "`n=== A4 - offline verification FROM THE MEDIUM ===`n"
    Assert-OutDirOutsideRepo
    $mnt = Get-MountPath
    $onMedium = Join-Path $mnt $TAR_NAME
    if (-not (Test-Path $onMedium)) { Die "$TAR_NAME not found on $mnt - run -Step A2 first" }
    Ok "verifying $onMedium (not the staging copy)"

    Push-Location $RepoRoot
    try   { $out = & $Python $Verifier --verify $onMedium "sha256:$OUTER_SHA" 2>&1 | Out-String }
    finally { Pop-Location }
    Say $out

    $fail = @()
    if ($out -notmatch 'VERDICT:\s*PASS')                             { $fail += 'no PASS verdict' }
    if ($out -notmatch [regex]::Escape($OUTER_SHA))                   { $fail += 'outer digest absent' }
    if ($out -notmatch [regex]::Escape($INNER_SHA))                   { $fail += 'inner/semantic digest absent' }
    if ($out -notmatch 'bound identity\s*:\s*MATCHES')                { $fail += 'bound identity not MATCHES' }
    if ($out -notmatch 'objects present\s*:\s*13\s+referenced:\s*13') { $fail += 'object count != 13/13' }
    if ($fail.Count) { Die ("verification INCOMPLETE: " + ($fail -join '; ')) }
    Ok "PASS - outer, inner, 13/13 objects, bound identity MATCHES"

    if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }
    $stamp  = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    $record = Join-Path $OutDir "MR002_WPA_A4_Verdict_$((Get-Date).ToString('yyyyMMdd')).txt"
@"
MR-002 WP-A / A4 - offline verification from the medium
=======================================================
UTC timestamp        : $stamp
Verified from        : $onMedium  (removable medium, NOT staging)
Outer (wrapper)      : sha256:$OUTER_SHA
Inner (semantic)     : sha256:$INNER_SHA
Objects              : 13 present / 13 referenced
Bound identity       : MATCHES
Verdict              : PASS
Network / AWS used   : none (offline verifier)

Scope: closes a custody gap only. Governing invariant 10 - no passing recovery
verification satisfies Requirement 7 or authorizes execution.

--- section 7 custodian record: TO BE COMPLETED BY THE OWNER -------------------
Human custodian      : (RECOVERY-MEDIA custodian - a real accountable individual)
                       NOTE: this does NOT satisfy the Step 2 OPERATIONAL custodian.
                       One person may hold both, but only by explicit appointment
                       recorded in BOTH places.
Media identifier     : (non-sensitive label only - no serial numbers)
Physical storage     : offline removable, normally disconnected
Encrypted at rest    : yes - VeraCrypt volume-level, AES/SHA-512 (METHOD ONLY)
Creation date        : 2026-07-22 (archive) / (media write date)
Last verification    : $stamp
Review cadence       : quarterly (recommended)
Normally disconnected: (yes/no)
Cloud-synchronized   : staging: no / medium: (record)

NEVER record here: keys, passphrases, recovery phrases, serial numbers, or
precise physical locations.
"@ | Set-Content -Path $record -Encoding UTF8
    Ok "verdict recorded: $record"
    Say "`nNext: -Step A3 -MountLetter $MountLetter`n"
}

'A3' {
    Say "`n=== A3 - dismount and disconnect ===`n"
    & $VeraCrypt /d $MountLetter /q | Out-Null
    Start-Sleep -Seconds 2
    if (Test-Path "${MountLetter}:") { Warn "${MountLetter}: still visible - dismount manually in VeraCrypt" }
    else { Ok "volume dismounted" }
    Say @"
  Now, physically:
    1. Eject the USB device through Windows
    2. Unplug it
    3. Store it away from this workstation

  ** Windows will offer to FORMAT the drive because it cannot read an encrypted
     volume. DECLINE. Accepting destroys the copy. Eject promptly. **

  'Normally disconnected' is the property being bought: a drive that lives
  plugged into this workstation inherits its threats and is not independent.

  A5 (custodian record) and A6 (staging disposal) were completed 2026-08-10.
  WP-A is CLOSED; INDEPENDENT_OFFLINE_RECOVERY_COPY = CREATED.

  If you are RE-RUNNING this procedure onto fresh media, note the ordering that
  made the 2026-08-10 accidental format a 20-minute setback rather than an
  unrecoverable one:
    - A6 (staging disposal) comes strictly AFTER A5, and
    - never delete staging until -Step A4 returns PASS against the new medium.
  Staging now holds only the record JSON; the medium and ECR are the copies.
"@
}

}
