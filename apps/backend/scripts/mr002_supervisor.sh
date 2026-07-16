#!/bin/sh
# MR-002 full-population supervisor.
#
# Purpose: survive ENVIRONMENTAL crashes (the Windows/Docker FUSE Errno-5 append failures that
# killed the first detached run) WITHOUT ever auto-resuming past a genuine scientific STOP.
# The runner exits 1 for BOTH a crash and a STOP, so the supervisor must discriminate — and that
# discrimination is the whole safety property. Getting it wrong either strands a completed run or,
# far worse, LAUNDERS a preserved-and-halt verdict into a resume.
#
# ORDER OF CHECKS — deliberate, and different from the original:
#
#   1. STOP       — safety-critical, therefore checked FIRST. Nothing may mask it.
#   2. exit 0     — AUTHORITATIVE completion. The runner returns 0 only on a completed run.
#   3. banner     — ADVISORY only, matched loosely.
#   4. otherwise  — environmental crash: resume from the checkpoint.
#
# ⚠ WHY (2) AND (3) ARE IN THAT ORDER AND NOT REVERSED — learned 2026-07-16.
# The original checked the banner FIRST and gated on the exact string "FULL POPULATION: PASS".
# The countersigned row-2307 amendment renamed the banner to "FULL POPULATION — AMENDED PASS"
# (§5: a bare "PASS" would misrepresent an amended run), which silently killed the exact match.
# The run completed correctly and the supervisor logged "exit 0 without PASS marker; treating as
# completed" — benign only because the exit-0 branch caught it. Two lessons, both encoded here:
#   * NEVER gate control flow on human-readable prose. Prose changes; exit codes are the contract.
#   * The STOP check must not sit BEHIND a prose match that could preempt it.
#
# Hot checkpoint lives on the named volume /ckpt (ext4 in the WSL2 VM) to avoid the FUSE append
# failures. /out (bind mount) receives only the runner's final-artifact writes plus checkpoint
# copies. Relocating the checkpoint is science-neutral: the path is recorded honestly in the
# artifact and the exact outputs/hashes are path-independent.
set -u
CKPT=/ckpt/MR002_FullPopulation_checkpoint.jsonl
LOG=/ckpt/supervised.log
RUNNER=/work/apps/backend/scripts/mr002_full_population.py
MAX=300
n=0
echo "=== supervisor start $(date -u) ===" >> "$LOG"
echo "seeded checkpoint lines: $(wc -l < "$CKPT" 2>/dev/null || echo 0)" >> "$LOG"

mirror() {
  cp "$CKPT" /out/MR002_FullPopulation_checkpoint.jsonl 2>>"$LOG" || \
    echo "warn: ckpt copy failed" >> "$LOG"
}

while [ "$n" -lt "$MAX" ]; do
  n=$((n + 1))
  echo "--- attempt $n start $(date -u) ---" >> "$LOG"
  MR002_CHECKPOINT="$CKPT" MR002_OUT=/out \
    python "$RUNNER" > "/ckpt/attempt_${n}.out" 2> "/ckpt/attempt_${n}.err"
  code=$?
  lines=$(wc -l < "$CKPT" 2>/dev/null || echo 0)
  echo "attempt $n exit=$code checkpoint_lines=$lines $(date -u)" >> "$LOG"

  # ---- 1. SCIENTIFIC STOP — FIRST. A preserved-and-halt verdict outranks everything. ----------
  if grep -q "^STOP:" "/ckpt/attempt_${n}.err" 2>/dev/null; then
    echo "SCIENTIFIC STOP detected -- halting, NOT resuming (preserved for adjudication)" >> "$LOG"
    grep "^STOP:" "/ckpt/attempt_${n}.err" >> "$LOG" 2>/dev/null
    mirror
    echo "=== supervisor HALT (scientific STOP) attempt $n $(date -u) ===" >> "$LOG"
    exit 2
  fi

  # ---- 2. exit 0 is the AUTHORITATIVE completion signal ---------------------------------------
  if [ "$code" -eq 0 ]; then
    # The banner is advisory. Matched loosely so a future rewording cannot silently break this,
    # and recorded either way — its ABSENCE is worth seeing in the log, never worth acting on.
    if grep -Eq "FULL POPULATION.*PASS" "/ckpt/attempt_${n}.out" 2>/dev/null; then
      echo "completion banner: $(grep -Eo 'FULL POPULATION.*PASS' "/ckpt/attempt_${n}.out" | head -1)" >> "$LOG"
    else
      echo "note: exit 0 with no recognisable completion banner (advisory only; exit 0 governs)" >> "$LOG"
    fi
    mirror
    echo "=== supervisor DONE (exit 0) attempt $n $(date -u) ===" >> "$LOG"
    exit 0
  fi

  # ---- 3. environmental crash -> resume from the checkpoint ------------------------------------
  echo "environmental crash (exit=$code, no STOP marker); resuming in 5s" >> "$LOG"
  tail -3 "/ckpt/attempt_${n}.err" >> "$LOG" 2>/dev/null
  mirror
  sleep 5
done

echo "=== supervisor GAVE UP after MAX=$MAX attempts $(date -u) ===" >> "$LOG"
mirror
exit 3
