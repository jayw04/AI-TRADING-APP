#!/usr/bin/env bash
set -uo pipefail
cd /tmp/s1 && rm -rf bundle22 && mkdir bundle22 && tar xzf bundle22.tgz -C bundle22
R=/opt/workbench/data/research/range002_run
S1=/opt/workbench/data/research/range002_s1
sha() { sudo sha256sum "$1" | cut -d' ' -f1; }
sudo test ! -e $R/out_2017h1_eval_audit || { echo "audit dir exists"; exit 2; }
sudo mkdir -p $R/out_2017h1_eval_audit
CLS=$(sha $R/out_2017h1_census/census_classification.json); MAN=$(sha $R/census_manifest_2017h1.json)
sudo docker run --rm --network none --entrypoint python \
  -v $S1:/app/data/research/range002_s1:ro \
  -v /opt/workbench/data/research/range002_registry:/app/data/research/range002_registry:rw \
  -v $R:/app/data/research/range002_run:ro -v $R/out_2017h1_eval_audit:/audit_out:rw \
  -v /tmp/s1/bundle22:/work:ro trading-workbench-backend -I \
  /work/apps/backend/scripts/research/range002/audit_replay_run.py \
  --parent-run-id range002-run-000033 --audit-id AUDIT-RANGE002-2017H1-20261013-EVAL \
  --spec /work/docs/implementation/evidence/range_002/RANGE-002_Screen_Spec_Frozen_CostAware_v0.7_P_PLUS_E.json \
  --registry /app/data/research/range002_registry/range002_runs.jsonl \
  --parent-report /app/data/research/range002_run/out_2017h1_eval/report.json \
  --parent-evidence /app/data/research/range002_run/out_2017h1_acq/acquisition_evidence_range002-run-000019.json \
  --mapping /app/data/research/range002_run/symbol_mapping_2017h1.json \
  --universe /app/data/research/range002_s1/universe-2017h1-20261013/universe_symbols.txt \
  --price-tolerance 0.05 --price-max-mismatch-fraction 0.10 \
  --daily-snapshot /app/data/research/range002_s1/sharadar-2017h1-20261013 \
  --snapshot-manifest /app/data/research/range002_run/snapshot_manifest_2017h1_accepted.json \
  --minute-bars /app/data/research/range002_run/minute_bars_2017h1.duckdb \
  --minute-feed sip --minute-ts-convention start --table-filter SEP --lookback-calendar-days 45 \
  --coverage-threshold 0.98 --or-completeness-threshold 0.98 --equity 100000 --tick 0.01 \
  --code-sha 0bc33212518d130f0c580816e69cea67d1ff0e99 --raw-vendor-rows-attested \
  --delisting-action-value delisted \
  --no-trade-evidence /app/data/research/range002_run/out_2017h1_census/census_classification.json \
  --no-trade-evidence-sha256 "$CLS" \
  --census-manifest /app/data/research/range002_run/census_manifest_2017h1.json \
  --census-manifest-sha256 "$MAN" --accounted-tiers both \
  --audit-log /app/data/research/range002_registry/range002_audit_log.jsonl \
  --out-dir /audit_out/audit 2>&1 | tail -6
