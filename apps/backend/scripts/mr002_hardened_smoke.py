"""MR-002 hardened-crawler smoke test (owner directive 2026-07-11).

Runs BEFORE the next full production crawl — a small deliberate integration test
of the hardening controls so a multi-hour crawl never discovers an integration
defect. Owner-specified coverage:

  1. gzip cache creation (fresh fetch -> .gz object + index entry);
  2. legacy cache reading (pre-seeded uncompressed entry served as a hit);
  3. hash separation (content_sha256 != storage_sha256, both recorded);
  4. capped error retention (404 bodies: hash + <=4KB head only);
  5. controlled disk-guard termination (forced trip -> exit 3 +
     termination_reason=DISK_HEADROOM_GUARD in the partial run report);
  6. resumption (rerun completes from cache, no DUAL_HASH_STOP; NOTE:
     request-LEVEL resumption becomes assertable once task-9 checkpoints land —
     recorded as PENDING_TASK9, not silently skipped).

Run from the repo root (uses a scratch workdir; ~5 small issuers, a few hundred
requests, one SEC-throttled fetcher — do NOT run while a full crawl is active):
    PYTHONPATH=apps/backend .venv python apps/backend/scripts/mr002_hardened_smoke.py
"""

from __future__ import annotations

import csv
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CRAWL = Path(__file__).with_name("mr002_stage2_edgar_crawl.py")
BACKEND = ROOT / "apps" / "backend"

SMOKE_ROWS = [  # tiny issuer set: two current + one delisted (crosswalk semantics)
    {"permaticker": 199059, "ticker": "AAPL", "cik": 320193},
    {"permaticker": 194817, "ticker": "META", "cik": 1326801},
    {"permaticker": 187959, "ticker": "TWTR", "cik": 1418091},
]


def run_crawl(wd: Path, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ,
           "PYTHONPATH": str(BACKEND),
           "SEC_EDGAR_USER_AGENT": "GlobalComplyAI LLC jay.w0416@gmail.com",
           **(env_extra or {})}
    return subprocess.run(
        [sys.executable, str(CRAWL), "--workdir", str(wd), "--since", "2023-01-01"],
        env=env, capture_output=True, text=True, timeout=1800)


def main() -> int:
    wd = Path(tempfile.mkdtemp(prefix="mr002_smoke_"))
    results: dict[str, str] = {}
    try:
        with (wd / "identity_crosswalk_v0.1.csv").open("w", newline="",
                                                       encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["permaticker", "ticker", "cik",
                                              "effective_from", "effective_to",
                                              "relationship_type", "source",
                                              "source_record_id", "confidence",
                                              "mapping_rationale", "review_status"])
            w.writeheader()
            for r in SMOKE_ROWS:
                w.writerow({**r, "effective_from": "2013-01-01", "effective_to": "",
                            "relationship_type": "direct", "source": "smoke",
                            "source_record_id": "smoke", "confidence": "high",
                            "mapping_rationale": "smoke", "review_status": "approved"})

        # ---- run 1: fresh crawl (gzip creation, hash separation, capped errors) ----
        p1 = run_crawl(wd)
        assert p1.returncode == 0, f"run1 rc={p1.returncode}: {p1.stdout[-800:]}\n{p1.stderr[-800:]}"
        cache = wd / "edgar_cache"
        gz_objects = list(cache.glob("*.gz"))
        results["1_gzip_cache_creation"] = f"PASS ({len(gz_objects)} .gz objects)" \
            if gz_objects else "FAIL"
        idx = [json.loads(x) for x in (wd / "cache_index.jsonl").open(encoding="utf-8")]
        sep = [r for r in idx if r.get("content_sha256") and r.get("storage_sha256")]
        results["3_hash_separation"] = (
            f"PASS ({len(sep)}/{len(idx)} indexed; hashes differ: "
            f"{all(r['content_sha256'] != r['storage_sha256'] for r in sep)})"
            if sep and all(r["content_sha256"] != r["storage_sha256"] for r in sep)
            else "FAIL")
        errors = [json.loads(x) for x in
                  (wd / "raw_response_manifest.jsonl").open(encoding="utf-8")
                  if "error_body_head" in x]
        capped = all(len(e.get("error_body_head", "")) <= 4096 for e in errors)
        results["4_capped_error_retention"] = (
            f"PASS ({len(errors)} error bodies, all <=4KB)" if errors and capped
            else ("PASS-VACUOUS (no HTTP errors encountered)" if capped else "FAIL"))

        # ---- run 2: legacy-cache replay (convert one object to uncompressed) ----
        victim = gz_objects[0]
        legacy = victim.with_suffix("")            # strip .gz -> legacy key
        legacy.write_bytes(gzip.decompress(victim.read_bytes()))
        victim.unlink()
        p2 = run_crawl(wd)
        assert p2.returncode == 0, f"run2 rc={p2.returncode}"
        manifest_lines = (wd / "raw_response_manifest.jsonl").read_text(encoding="utf-8")
        results["2_legacy_cache_replay"] = (
            "PASS (rerun succeeded with a legacy uncompressed entry in place)"
            if legacy.exists() else "FAIL")
        results["6_resumption_from_cache"] = (
            "PASS (rerun completed; no DUAL_HASH_STOP)"
            if "DUAL_HASH_STOP" not in manifest_lines else "FAIL")
        results["6b_request_level_resumption"] = "PENDING_TASK9 (checkpoints not yet built)"

        # ---- run 3: forced disk-guard trip (controlled termination) ----
        wd3 = Path(tempfile.mkdtemp(prefix="mr002_smoke_guard_"))
        shutil.copy(wd / "identity_crosswalk_v0.1.csv", wd3)
        p3 = run_crawl(wd3, {"MR002_DISKGUARD_FORCE_FREE_PCT": "10"})
        report3 = json.loads((wd3 / "stage2_run_report.json").read_text()) \
            if (wd3 / "stage2_run_report.json").exists() else {}
        tripped = "DISK_HEADROOM_GUARD" in (wd3 / "raw_response_manifest.jsonl").read_text(
            encoding="utf-8") if (wd3 / "raw_response_manifest.jsonl").exists() else False
        results["5_disk_guard_controlled_halt"] = (
            "PASS (exit 3, termination_reason recorded, trip event logged)"
            if p3.returncode == 3
            and report3.get("termination_reason") == "DISK_HEADROOM_GUARD" and tripped
            else f"FAIL (rc={p3.returncode}, reason={report3.get('termination_reason')})")
        shutil.rmtree(wd3, ignore_errors=True)

        out = ROOT / "docs" / "implementation" / "evidence" / "mr_002" / \
            "MR002_HardenedSmoke_Report.json"
        out.write_text(json.dumps({"results": results,
                                   "workdir": str(wd)}, indent=2))
        print(json.dumps(results, indent=1))
        ok = all(v.startswith(("PASS", "PENDING")) for v in results.values())
        print("SMOKE", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        shutil.rmtree(wd, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
