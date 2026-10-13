#!/usr/bin/env bash
# RANGE-002 2017-H1: step "classify-check" | "revalidate" | "evaluate". No network, no refetch.
set -uo pipefail
STEP="${1:?step}"
CODE="${2:?code sha}"
B=/tmp/s1/bundle21
R=/opt/workbench/data/research/range002_run
EV=/work/docs/implementation/evidence/range_002
SPEC=$EV/RANGE-002_Screen_Spec_Frozen_CostAware_v0.7_P_PLUS_E.json
LEDGER=$EV/RANGE-002_exposure_ledger_2026-10-13_rev7_planned.json
sha() { sudo sha256sum "$1" | cut -d' ' -f1; }
EVID=$(sha $R/out_2017h1_acq/acquisition_evidence_range002-run-000019.json)
VAL0=$(sha $R/out_2017h1_acq/acquisition_validation.json)
CLS=$(sha $R/out_2017h1_census/census_classification.json)
MAN=$(sha $R/census_manifest_2017h1.json)
dock() {
  sudo docker run --rm --network none --entrypoint python \
    -v /opt/workbench/data/research/range002_s1:/app/data/research/range002_s1:ro \
    -v /opt/workbench/data/research/range002_registry:/app/data/research/range002_registry:rw \
    -v $R:/app/data/research/range002_run:rw -v $B:/work:ro trading-workbench-backend -I "$@"
}
COMMON=(--spec "$SPEC" --registry /app/data/research/range002_registry/range002_runs.jsonl
  --exposure-ledger "$LEDGER"
  --daily-snapshot /app/data/research/range002_s1/sharadar-2017h1-20261013
  --snapshot-manifest /app/data/research/range002_run/snapshot_manifest_2017h1_accepted.json
  --minute-bars /app/data/research/range002_run/minute_bars_2017h1.duckdb
  --minute-feed sip --minute-ts-convention start --date-start 2017-01-01 --date-end 2017-06-30
  --table-filter SEP --lookback-calendar-days 45 --coverage-threshold 0.98 --or-completeness-threshold 0.98
  --equity 100000 --tick 0.01 --code-sha "$CODE" --raw-vendor-rows-attested
  --allow-sequential-pulls-ref "owner-instruction-2026-10-13:RANGE-002_Owner_Instruction_Record_2026-10-13_rev8.md"
  --delisting-action-value delisted
  --no-trade-evidence /app/data/research/range002_run/out_2017h1_census/census_classification.json
  --no-trade-evidence-sha256 "$CLS"
  --census-manifest /app/data/research/range002_run/census_manifest_2017h1.json
  --census-manifest-sha256 "$MAN" --accounted-tiers both)
case "$STEP" in
  classify-check)
    sudo test ! -e $R/out_2017h1_census/census_classification_recheck.json || exit 2
    dock /work/apps/backend/scripts/research/range002/classify_census.py \
      --manifest /app/data/research/range002_run/census_manifest_2017h1.json \
      --probe /app/data/research/range002_run/out_2017h1_census/census_probe.json \
      --out /app/data/research/range002_run/out_2017h1_census/census_classification_recheck.json | head -1
    echo "original=$CLS recheck=$(sha $R/out_2017h1_census/census_classification_recheck.json)"
    ;;
  revalidate)
    sudo test ! -e $R/out_2017h1_acq_rev2 || { echo "out_2017h1_acq_rev2 exists"; exit 2; }
    dock /work/apps/backend/scripts/research/range002/run_descriptive_screen.py "${COMMON[@]}" \
      --partition ACQUISITION --out-dir /app/data/research/range002_run/out_2017h1_acq_rev2 \
      --carry-acquisition-evidence /app/data/research/range002_run/out_2017h1_acq/acquisition_evidence_range002-run-000019.json \
      --carry-acquisition-evidence-sha256 "$EVID" \
      --linked-validation /app/data/research/range002_run/out_2017h1_acq/acquisition_validation.json \
      --linked-validation-sha256 "$VAL0" 2>&1 | tail -3
    ;;
  evaluate)
    VAL2=$(sha $R/out_2017h1_acq_rev2/acquisition_validation.json)
    sudo test ! -e $R/out_2017h1_eval || { echo "out_2017h1_eval exists"; exit 2; }
    dock /work/apps/backend/scripts/research/range002/run_descriptive_screen.py "${COMMON[@]}" \
      --partition DEVELOPMENT_SELECTION --out-dir /app/data/research/range002_run/out_2017h1_eval \
      --acquisition-validation /app/data/research/range002_run/out_2017h1_acq_rev2/acquisition_validation.json \
      --acquisition-validation-sha256 "$VAL2" 2>&1 | tail -3
    ;;
esac
