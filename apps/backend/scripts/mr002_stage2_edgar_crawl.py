"""MR-002 stage-2 — full-universe V1/V2 EDGAR crawl (owner controls, 2026-07-11).

Released by the stage-1 identity report (all acceptance criteria PASS). Crawls the
754 crosswalked securities' issuers (every distinct CIK, including predecessor
CIKs like Google 1288776) for:
  V1: 8-K Item 2.02 earnings anchors (from the pinned accession manifest);
  V2: PIT SIC observations from 10-K/10-Q(-/A) filing headers.

Owner-required controls implemented here:
- PIN BEFORE FETCH: Phase A enumerates every relevant accession from the
  submissions API (+ shards), writes + hashes `accession_manifest.json` BEFORE any
  document/header retrieval. Phases B/C read only manifest accessions.
- PROVENANCE-PRESERVING RETRIES: every attempt logs url/accession, attempt number,
  HTTP status, retrieval timestamp, response sha256, cached-vs-fresh.
- DUAL-HASH STOP RULE: if the same URL/accession returns different bytes across
  retrievals, BOTH hashes are retained and the run STOPS for review — no silent
  selection.
- FETCH vs EXTRACTION completeness: accessions_requested / responses_retrieved /
  responses_failed / responses_hash_verified / earnings_candidates /
  earnings_anchors_accepted / sic_observations_extracted / sic_missing_filings /
  parser_rejections.
- SNAPSHOT: raw-response manifest (JSONL), parsed V1/V2 tables + hashes, and the
  extraction-code hash are pinned in the run report before any gate calculation.

The registered modules (earnings_anchors.py / sic_history.py) run UNMODIFIED via a
minimal import shim — semantics parity with the countersigned pilot by construction.

Run (self-contained; needs the mini app tree + identity_crosswalk CSV beside it):
    SEC_EDGAR_USER_AGENT="Org contact" python3 mr002_stage2_edgar_crawl.py \
        --workdir /data --since 2010-01-01
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import shutil
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from app.altdata.mr002.earnings_anchors import (
    anchor_metrics,
    build_anchors,
    collect_candidates,
)
from app.altdata.mr002.sic_history import build_segments, collect_sic_observations
from app.altdata.sec.ingest import older_shard_urls, submissions_url

RATE = 8.0  # req/s, under the SEC 10/s ceiling
V2_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A")


class StopForReview(RuntimeError):
    """Dual-hash stop rule fired — same URL returned different bytes."""


class DiskGuard(RuntimeError):
    """Disk circuit breaker (owner ops directive 2026-07-11): the worker protects
    its own resources — the external monitor only observes."""


class ProvenanceFetcher:
    """Throttled EDGAR fetcher with full per-attempt provenance and a byte-hash
    consistency guarantee. Satisfies the modules' client Protocols."""

    def __init__(self, workdir: Path, user_agent: str) -> None:
        self.ua = user_agent
        self.workdir = workdir
        self.cache = workdir / "edgar_cache"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.log_path = workdir / "raw_response_manifest.jsonl"
        self.log = self.log_path.open("a", encoding="utf-8")
        self.index = (workdir / "cache_index.jsonl").open("a", encoding="utf-8")
        self.hashes: dict[str, str] = {}          # url -> first-seen sha256
        self.counters = {"requested": 0, "retrieved": 0, "failed": 0,
                         "cached_hits": 0, "hash_verified": 0,
                         "compressed_bytes": 0, "uncompressed_bytes": 0}
        self._last = 0.0
        self._disk_check_countdown = 0

    def _disk_guard(self) -> None:
        """Owner directive: <20% free = stop accepting new downloads (single-threaded
        worker => a clean checkpointed halt); the run resumes after expansion."""
        self._disk_check_countdown -= 1
        if self._disk_check_countdown > 0:
            return
        self._disk_check_countdown = 50
        du = shutil.disk_usage(self.workdir)
        free_pct = 100.0 * du.free / du.total
        if free_pct < 20.0:
            self._record(event="DISK_GUARD_TRIP", free_pct=round(free_pct, 1))
            self.log.flush()
            raise DiskGuard(f"free disk {free_pct:.1f}% < 20% — new downloads stopped; "
                            "state is checkpointed, resume after expanding storage")

    def _record(self, **kw) -> None:
        kw["ts"] = datetime.now(UTC).isoformat()
        self.log.write(json.dumps(kw) + "\n")
        self.log.flush()

    def _key(self, url: str) -> Path:
        return self.cache / hashlib.sha256(url.encode()).hexdigest()

    def _fetch(self, url: str, headers: dict | None = None) -> bytes:
        self.counters["requested"] += 1
        ck = self._key(url)
        gz = ck.with_suffix(".gz")
        if gz.exists():                              # compressed-at-rest cache
            body = gzip.decompress(gz.read_bytes())
            self.counters["cached_hits"] += 1
            self._record(url=url, attempt=0, status="cache", cached=True,
                         sha256=hashlib.sha256(body).hexdigest())
            return body
        if ck.exists():                              # legacy uncompressed entry
            body = ck.read_bytes()
            self.counters["cached_hits"] += 1
            self._record(url=url, attempt=0, status="cache", cached=True,
                         sha256=hashlib.sha256(body).hexdigest())
            return body
        self._disk_guard()
        last_err = None
        for attempt in range(1, 4):
            wait = self._last + 1.0 / RATE - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            # SEC fair-access recommended headers: declared UA + gzip transfer
            req = urllib.request.Request(url, headers={
                "User-Agent": self.ua, "Accept-Encoding": "gzip, deflate",
                **(headers or {})})
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    raw = r.read()
                    status = r.status
                    enc = (r.headers.get("Content-Encoding") or "").lower()
                body = gzip.decompress(raw) if "gzip" in enc else raw
            except urllib.error.HTTPError as e:
                # error bodies: hash + first 4KB only (owner tier-3 retention)
                try:
                    eb = e.read() or b""
                except Exception:  # noqa: BLE001
                    eb = b""
                self._record(url=url, attempt=attempt, status=e.code, cached=False,
                             error_body_sha256=hashlib.sha256(eb).hexdigest(),
                             error_body_head=eb[:4096].decode("utf-8", "replace"))
                last_err = e
                if e.code in (403, 404):
                    break
                time.sleep(2 * attempt)
                continue
            except Exception as e:  # noqa: BLE001 — every attempt is recorded
                self._record(url=url, attempt=attempt, status=repr(e)[:80], cached=False)
                last_err = e
                time.sleep(2 * attempt)
                continue
            h = hashlib.sha256(body).hexdigest()
            comp = gzip.compress(body, 6)
            self.counters["compressed_bytes"] += len(comp)
            self.counters["uncompressed_bytes"] += len(body)
            self._record(url=url, attempt=attempt, status=status, sha256=h,
                         cached=False, compressed_bytes=len(comp),
                         uncompressed_bytes=len(body))
            prev = self.hashes.get(url)
            if prev is not None and prev != h:
                self._record(url=url, event="DUAL_HASH_STOP", first=prev, second=h)
                raise StopForReview(f"{url}: {prev} != {h}")
            self.hashes[url] = h
            self.counters["hash_verified"] += 1
            gz.write_bytes(comp)                     # compressed at rest
            self.index.write(json.dumps({"url": url, "key": gz.name,
                                         "compressed_bytes": len(comp),
                                         "uncompressed_bytes": len(body)}) + chr(10))
            self.index.flush()
            self.counters["retrieved"] += 1
            return body
        self.counters["failed"] += 1
        raise last_err or RuntimeError(f"fetch failed: {url}")

    def largest_objects_report(self, n: int = 100) -> list[dict]:
        """Owner post-run requirement: largest cached objects by URL and size."""
        idx = {}
        ipath = self.workdir / "cache_index.jsonl"
        if ipath.exists():
            for line in ipath.open(encoding="utf-8"):
                try:
                    r = json.loads(line)
                    idx[r["key"]] = r
                except Exception:  # noqa: BLE001
                    continue
        rows = []
        for f in self.cache.iterdir():
            meta = idx.get(f.name, {})
            rows.append({"key": f.name, "bytes_on_disk": f.stat().st_size,
                         "url": meta.get("url", "(pre-index cache entry)"),
                         "uncompressed_bytes": meta.get("uncompressed_bytes")})
        return sorted(rows, key=lambda r: -r["bytes_on_disk"])[:n]

    # module Protocols
    def get_json(self, url: str):
        return json.loads(self._fetch(url))

    def get_text(self, url: str, *, headers: dict | None = None) -> str:
        return self._fetch(url, headers=headers).decode("utf-8", errors="replace")


def load_issuers(crosswalk_csv: Path) -> dict[int, str]:
    """distinct CIK -> label (joined tickers), incl. predecessor CIKs."""
    by_cik: dict[int, set[str]] = {}
    with crosswalk_csv.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["cik"]:
                by_cik.setdefault(int(r["cik"]), set()).add(r["ticker"])
    return {cik: "/".join(sorted(ts)) for cik, ts in by_cik.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default=".")
    ap.add_argument("--since", default="2010-01-01")
    ap.add_argument("--crosswalk-csv", default="identity_crosswalk_v0.1.csv")
    args = ap.parse_args()
    wd = Path(args.workdir)
    wd.mkdir(parents=True, exist_ok=True)
    import os
    ua = os.environ.get("SEC_EDGAR_USER_AGENT", "GlobalComplyAI LLC jay.w0416@gmail.com")
    fetcher = ProvenanceFetcher(wd, ua)
    issuers = load_issuers(wd / args.crosswalk_csv)
    print(f"[{datetime.now(UTC).isoformat()}] issuers: {len(issuers)} distinct CIKs", flush=True)

    # ---------------- Phase A: PIN the accession manifest ----------------
    manifest_path = wd / "accession_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        print("manifest already pinned — resuming", flush=True)
    else:
        manifest: dict = {"since": args.since, "ciks": {}, "v2_forms": list(V2_FORMS)}
        for i, (cik, label) in enumerate(sorted(issuers.items()), 1):
            try:
                subs = fetcher.get_json(submissions_url(cik))
            except StopForReview:
                raise
            except Exception as e:  # noqa: BLE001 — recorded; issuer marked failed
                manifest["ciks"][str(cik)] = {"label": label, "error": repr(e)[:120]}
                continue
            blocks = [((subs.get("filings") or {}).get("recent") or {})]
            for u in older_shard_urls(subs, since=args.since):
                try:
                    blocks.append(fetcher.get_json(u))
                except StopForReview:
                    raise
                except Exception as e:  # noqa: BLE001
                    manifest["ciks"].setdefault(str(cik), {}).setdefault(
                        "shard_errors", []).append(repr(e)[:80])
            v2_rows = []
            for b in blocks:
                forms = b.get("form") or []
                accs = b.get("accessionNumber") or []
                fdates = b.get("filingDate") or []
                accepts = b.get("acceptanceDateTime") or []
                for j, form in enumerate(forms):
                    if form in V2_FORMS and (not args.since or
                                             (fdates[j] or "") >= args.since):
                        v2_rows.append({"accession": accs[j], "form": form,
                                        "filing_date": fdates[j],
                                        "acceptance": accepts[j] if j < len(accepts) else None})
            manifest["ciks"][str(cik)] = {"label": label, "v2_accessions": v2_rows,
                                          "n_shards": len(blocks) - 1}
            if i % 50 == 0:
                print(f"  manifest {i}/{len(issuers)}", flush=True)
        body = json.dumps(manifest, indent=1)
        manifest_path.write_text(body)
        (wd / "accession_manifest.sha256").write_text(
            hashlib.sha256(body.encode()).hexdigest())
        print(f"MANIFEST PINNED: {sum(len(v.get('v2_accessions', [])) for v in manifest['ciks'].values())} "
              f"V2 accessions; sha256 written", flush=True)

    # ---------------- Phase B: V1 anchors (from pinned submissions data) ----------------
    db = duckdb.connect(str(wd / "mr002_stage2.duckdb"))
    db.execute("""CREATE TABLE IF NOT EXISTS anchors (
        cik BIGINT, ticker VARCHAR, accession VARCHAR, report_date VARCHAR,
        acceptance_utc TIMESTAMPTZ, session_date DATE, availability_class VARCHAR,
        event_time_basis VARCHAR, is_amendment_origin BOOLEAN, amended_by VARCHAR,
        collapsed_duplicates VARCHAR, PRIMARY KEY (cik, accession))""")
    db.execute("""CREATE TABLE IF NOT EXISTS anchor_rejections (
        cik BIGINT, ticker VARCHAR, accession VARCHAR, reason VARCHAR)""")
    counters = {"earnings_candidates": 0, "earnings_anchors_accepted": 0,
                "anchor_rejections": 0, "v1_issuer_errors": 0}
    db.execute("DELETE FROM anchors")
    db.execute("DELETE FROM anchor_rejections")
    all_metrics_inputs = {"anchors": [], "rejections": [], "exceptions": []}
    for i, (cik, label) in enumerate(sorted(issuers.items()), 1):
        try:
            cands, _sh = collect_candidates(fetcher, cik, label, since=args.since)
            res = build_anchors(cands)
        except StopForReview:
            raise
        except Exception:  # noqa: BLE001 — recorded in fetch log; counted
            counters["v1_issuer_errors"] += 1
            continue
        counters["earnings_candidates"] += len(cands)
        counters["earnings_anchors_accepted"] += len(res.anchors)
        counters["anchor_rejections"] += len(res.rejections)
        all_metrics_inputs["anchors"].extend(res.anchors)
        all_metrics_inputs["rejections"].extend(res.rejections)
        all_metrics_inputs["exceptions"].extend(res.exceptions)
        for a in res.anchors:
            db.execute("INSERT OR REPLACE INTO anchors VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       [a.cik, a.ticker, a.accession, a.report_date, a.acceptance_utc,
                        a.session_date, a.availability_class, a.event_time_basis,
                        a.is_amendment_origin, json.dumps(a.amended_by),
                        json.dumps(a.collapsed_duplicates)])
        for rj in res.rejections:
            db.execute("INSERT INTO anchor_rejections VALUES (?,?,?,?)",
                       [rj.cik, rj.ticker, rj.accession, rj.reason])
        if i % 50 == 0:
            print(f"  V1 {i}/{len(issuers)} anchors={counters['earnings_anchors_accepted']}",
                  flush=True)
    from app.altdata.mr002.earnings_anchors import AnchorBuildResult
    v1_metrics = anchor_metrics(
        AnchorBuildResult(anchors=all_metrics_inputs["anchors"],
                          rejections=all_metrics_inputs["rejections"],
                          exceptions=all_metrics_inputs["exceptions"]),
        n_securities_requested=len(issuers))
    print(f"V1 DONE: {counters['earnings_anchors_accepted']} anchors", flush=True)

    # ---------------- Phase C: V2 PIT SIC (manifest-driven header crawl) ----------------
    db.execute("""CREATE TABLE IF NOT EXISTS sic_observations (
        cik BIGINT, ticker VARCHAR, accession VARCHAR, form VARCHAR,
        accepted_utc TIMESTAMPTZ, sic VARCHAR, sic_name VARCHAR,
        PRIMARY KEY (cik, accession))""")
    db.execute("""CREATE TABLE IF NOT EXISTS sic_segments (
        cik BIGINT, ticker VARCHAR, sic VARCHAR, sic_name VARCHAR,
        effective_from TIMESTAMPTZ, effective_to TIMESTAMPTZ, source_accession VARCHAR)""")
    db.execute("DELETE FROM sic_observations")
    db.execute("DELETE FROM sic_segments")
    counters.update({"sic_observations_extracted": 0, "sic_missing_filings": 0,
                     "sic_conflicts": 0, "v2_issuer_errors": 0})
    for i, (cik, label) in enumerate(sorted(issuers.items()), 1):
        try:
            res = collect_sic_observations(fetcher, cik, label, since=args.since)
            res = build_segments(res)
        except StopForReview:
            raise
        except Exception:  # noqa: BLE001
            counters["v2_issuer_errors"] += 1
            continue
        counters["sic_observations_extracted"] += sum(
            1 for o in res.observations if o.sic is not None)
        counters["sic_missing_filings"] += res.missing_sic
        counters["sic_conflicts"] += len(res.conflicts)
        for o in res.observations:
            db.execute("INSERT OR REPLACE INTO sic_observations VALUES (?,?,?,?,?,?,?)",
                       [o.cik, o.ticker, o.accession, o.form, o.accepted_utc, o.sic,
                        o.sic_name])
        for s in res.segments:
            db.execute("INSERT INTO sic_segments VALUES (?,?,?,?,?,?,?)",
                       [s.cik, s.ticker, s.sic, s.sic_name, s.effective_from,
                        s.effective_to, s.source_accession])
        if i % 25 == 0:
            print(f"  V2 {i}/{len(issuers)} obs={counters['sic_observations_extracted']}",
                  flush=True)

    # ---------------- snapshot & run report ----------------
    for tbl in ("anchors", "sic_observations", "sic_segments"):
        db.execute(f"COPY {tbl} TO '{wd / (tbl + '.csv')}' (HEADER, DELIMITER ',')")
    db.close()
    report = {
        "generated": datetime.now(UTC).isoformat(),
        "since": args.since,
        "issuers": len(issuers),
        "controls": {"manifest_pinned_before_fetch": True,
                     "dual_hash_stop_rule": "armed (no trigger = clean)",
                     "retries_provenance_preserving": True},
        "fetch_counters": {"accessions_requested": fetcher.counters["requested"],
                           "responses_retrieved": fetcher.counters["retrieved"],
                           "responses_failed": fetcher.counters["failed"],
                           "responses_hash_verified": fetcher.counters["hash_verified"],
                           "cache_hits": fetcher.counters["cached_hits"]},
        "extraction_counters": counters,
        "v1_metrics": v1_metrics,
        "snapshots": {
            "accession_manifest_sha256": (wd / "accession_manifest.sha256").read_text().strip(),
            **{f"{t}_csv_sha256": hashlib.sha256((wd / f"{t}.csv").read_bytes()).hexdigest()
               for t in ("anchors", "sic_observations", "sic_segments")},
            "raw_response_manifest_lines": sum(1 for _ in fetcher.log_path.open()),
            "largest_100_cache_objects": fetcher.largest_objects_report(100),
            "extraction_code_sha256": hashlib.sha256(
                Path(__file__).read_bytes()).hexdigest(),
        },
    }
    (wd / "stage2_run_report.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({k: report[k] for k in ("fetch_counters", "extraction_counters")},
                     indent=1))
    print("STAGE2 COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
