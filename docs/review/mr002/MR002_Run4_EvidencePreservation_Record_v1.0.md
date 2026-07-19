# MR-002 Run-4 Evidence Preservation Record v1.0

Executed 2026-07-19 ~11:03Z per the run-4 evidence-replay verdict, immediately before
stopping (NOT terminating) the launch host. All operations no-overwrite; all hashes
verified pre- and post-move.

## Archival operation

Archive destination (fresh; refused if preexisting): `/home/ec2-user/mr002/evidence/run4_replay_defect/`

| File | SHA-256 pre-move | SHA-256 post-move | Bytes |
|---|---|---|---|
| `MR002_Stage3_CleanRun_checkpoint.jsonl` | `b9b0a94817deb540d768fc5b5909978e22f40f04e40a81e1bd5733a6637b7445` | identical | 67,293,482 (3,896 lines) |
| `MR002_Stage3_CleanRun_Manifest.json` | `1132d3b8a3feeefe8c92107468b488cd31da52ec67df4abd78567d8879c96e40` | identical | 130,846 |

Row-manifest SHA-256 (inside the manifest): `699b17dffd222c06392842f58841f185e74132331e67f40df26817a94d7ac7eb`.

Moved with `mv -n` (rename, same filesystem). Locked: files `444 root:root`, archive
dirs `555 ec2-user`. `~/mr002/out/cleanrun` removed after the move; `~/mr002/out` is
now EMPTY and `cleanrun` will be recreated ONLY when a Run-5 chain is authorized.
The Run-4 checkpoint is immutable defect evidence — reuse for execution or resume is
FORBIDDEN per the verdict.

## Pre-stop state record

- **Staged inputs (9/9, unchanged):** authorization `487c6ecb…`, execution_binding
  `83d1bcbf…`, execution_package `66c8d42f…`, expected_pins `ddfa43d0…`,
  final_test_report `26bbdff8…`, launch_attestation `7c65a901…`,
  launch_verification_receipt `6462e6c8…`, realism_pass `f7cccd65…`,
  source_manifest `27d2819b…` (full 64-hex values in the v4 chain records and stop
  report v4.0).
- **Launcher checkout** `~/mr002/repo`: commit `b6e5d278ff5caf843e1081ab27ff91473a1126ce`,
  tree `1657d0c768ea103acd1a16722ee90ef40e1da47d`, porcelain EMPTY.
- **Numerical checkout** `~/mr002/numrepo`: commit `d26bd9edbd875d2e3e11d4a6f6e06bad933b168e`,
  tree `c0e52d8ec61f881a2058c9c9686fde1ec33123a0`, porcelain EMPTY.
- **Containers:** `docker ps -a` count 0.
- **Image:** `sha256:81e8d7a7be6bb022d7bde68e923ea6ef2a41b029390200e0240235f35aa173ea`
  present and inspectable.
- **Signing keys:** `/home/ec2-user/keys/mr002_launcher_ed25519.pem` mode **600**
  ec2-user (private), `.pub.pem` 664 — on the root EBS filesystem.
- **Persistent storage:** the host is EBS-only — single disk `nvme0n1` (30G xfs `/`,
  plus EFI). c6a.large has NO instance-store volumes; ALL governed evidence, keys,
  checkouts, and inputs reside on the root EBS volume and survive a stop.
- **Validation / OOS:** SEALED AND UNREAD — the run accessed the DEV window only
  (frozen corpus source, 2013-01-02 → 2019-10-02); no session has read validation or
  OOS data.

## Instance identity

| Item | Value |
|---|---|
| Instance ID | `i-0f3ceafdd4294c572` |
| Type / AZ | `c6a.large` / `us-east-1d` |
| AMI device mappings | `ami`, `root` (IMDS); API: `/dev/xvda` |
| EBS volume | `vol-0ce8c0056244d14f5` at `/dev/xvda`, **DeleteOnTermination=true** |
| Account / operator | `219024422756` / `arn:aws:iam::219024422756:user/JayWang` |

⚠ `DeleteOnTermination=true` means TERMINATION WOULD DESTROY THE EVIDENCE VOLUME.
Stop preserves it. Termination is NOT AUTHORIZED (verdict).

## Disposition

Instance STOPPED (not terminated) via `aws ec2 stop-instances` after this record.
Stopping consumes the continuously-qualified runtime state: before any v1.8
qualification or Run 5 on restart, a FULL host requalification is required (CPU,
kernel, Docker, snapshotter, image/config digest, volumes, permissions, checkouts,
keys, inputs, symlinks, containers, output-root state).
