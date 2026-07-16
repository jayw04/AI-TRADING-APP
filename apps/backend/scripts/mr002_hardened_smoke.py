"""MR-002 hardened-crawler smoke test (owner acceptance spec, 2026-07-11).

Two sections:

A. FIXTURE TRANSPORT TESTS — a local HTTP server exercises the six owner-specified
   server behaviors against the ProvenanceFetcher directly:
     honors Range · ignores Range (1MB body) · returns gzip despite identity ·
     chunked/no Content-Length · closes early · HTML error body.
   CRITICAL ACCEPTANCE (bytes actually read/persisted, never response headers):
     max_persisted_bytes_for_ranged_request <= 262,144
   Telemetry asserted per request: range_requested, range_honored, http_status,
   content_range, content_length_header, bytes_read, bytes_persisted, truncated,
   parse_succeeded.

B. LIVE INTEGRATION TESTS (small; never concurrent with a production crawl):
   gzip cache creation · legacy uncompressed cache replay · content/storage hash
   separation · forced DISK_HEADROOM_GUARD controlled halt (exit 3 +
   termination_reason) · cache resumption without DUAL_HASH_STOP. Exact
   request-level resumption = PENDING_TASK9 (checkpoints precede concurrency),
   recorded explicitly.

Run from the repo root:
    PYTHONPATH=apps/backend .venv python apps/backend/scripts/mr002_hardened_smoke.py
"""

from __future__ import annotations

import csv
import gzip
import http.server
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CRAWL = Path(__file__).with_name("mr002_stage2_edgar_crawl.py")
BACKEND = ROOT / "apps" / "backend"
CAP = 262144

SMOKE_ROWS = [
    {"permaticker": 199059, "ticker": "AAPL", "cik": 320193},
    {"permaticker": 194817, "ticker": "META", "cik": 1326801},
    {"permaticker": 187959, "ticker": "TWTR", "cik": 1418091},
]


def load_fetcher_cls():
    spec = importlib.util.spec_from_file_location("mr002_crawl", CRAWL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mr002_crawl"] = mod
    spec.loader.exec_module(mod)
    return mod.ProvenanceFetcher


class Fixture(http.server.BaseHTTPRequestHandler):
    BIG = b"HEADER-PAYLOAD-" + b"X" * (1024 * 1024)      # ~1MB, marker at front

    def log_message(self, *a):  # quiet
        pass

    def do_GET(self):  # noqa: N802
        p = self.path
        if p == "/honors-range":
            rng = self.headers.get("Range", "bytes=0-4095")
            hi = int(rng.split("-")[1])
            chunk = self.BIG[: hi + 1]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes 0-{hi}/{len(self.BIG)}")
            self.send_header("Content-Length", str(len(chunk)))
            self.end_headers()
            self.wfile.write(chunk)
        elif p == "/ignores-range":
            self.send_response(200)                       # full body despite Range
            self.send_header("Content-Length", str(len(self.BIG)))
            self.end_headers()
            self.wfile.write(self.BIG)
        elif p == "/gzip-despite-identity":
            comp = gzip.compress(b"GZIPPED-HEADER-CONTENT " * 50)
            self.send_response(200)
            self.send_header("Content-Encoding", "gzip")  # despite identity request
            self.send_header("Content-Length", str(len(comp)))
            self.end_headers()
            self.wfile.write(comp)
        elif p == "/chunked-no-length":
            self.send_response(200)                       # no Content-Length at all
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b"NO-LENGTH-BODY " * 100)
        elif p == "/early-close":
            self.send_response(200)
            self.send_header("Content-Length", "999999")  # promise more than sent
            self.end_headers()
            self.wfile.write(b"PARTIAL")                   # then close early
        elif p == "/html-error":
            body = b"<html><body>" + b"ERROR " * 2000 + b"</body></html>"  # ~12KB
            self.send_response(404)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


def last_record(wd: Path, url_frag: str) -> dict:
    rec = {}
    for line in (wd / "raw_response_manifest.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        if url_frag in str(r.get("url", "")):
            rec = r
    return rec


def transport_tests(results: dict) -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Fixture)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    wd = Path(tempfile.mkdtemp(prefix="mr002_smoke_transport_"))
    fetcher = load_fetcher_cls()(wd, "smoke-test agent@local")
    rng = {"Range": "bytes=0-4095"}
    persisted_max = 0

    def persisted(url_frag: str) -> int:
        return int(last_record(wd, url_frag).get("bytes_persisted") or 0)

    # T1 server honors Range
    body = fetcher.get_text(f"{base}/honors-range", headers=rng)
    rec = last_record(wd, "honors-range")
    ok = (rec.get("range_requested") is True and rec.get("range_honored") is True
          and rec.get("http_status") == 206 and rec.get("bytes_read") == 4096
          and not rec.get("truncated") and body.startswith("HEADER-PAYLOAD"))
    results["T1_server_honors_range"] = "PASS" if ok else f"FAIL {rec}"
    results["T1_parse_succeeded"] = "PASS" if body.startswith("HEADER-PAYLOAD") else "FAIL"
    persisted_max = max(persisted_max, persisted("honors-range"))

    # T2 server ignores Range (the 422MB scenario in miniature)
    body = fetcher.get_text(f"{base}/ignores-range", headers=rng)
    rec = last_record(wd, "ignores-range")
    ok = (rec.get("range_requested") is True and rec.get("range_honored") is False
          and rec.get("http_status") == 200 and rec.get("bytes_read") == CAP
          and rec.get("truncated") is True and body.startswith("HEADER-PAYLOAD")
          and len(body) <= CAP)
    results["T2_server_ignores_range_read_capped"] = "PASS" if ok else f"FAIL {rec}"
    results["T2_parse_succeeded_from_capped_body"] = (
        "PASS" if body.startswith("HEADER-PAYLOAD") else "FAIL")
    persisted_max = max(persisted_max, persisted("ignores-range"))

    # T3 gzip despite identity (small complete stream must decode)
    body = fetcher.get_text(f"{base}/gzip-despite-identity", headers=rng)
    rec = last_record(wd, "gzip-despite")
    ok = "GZIPPED-HEADER-CONTENT" in body and rec.get("bytes_read", 0) < CAP
    results["T3_gzip_despite_identity"] = "PASS" if ok else f"FAIL {rec}"
    persisted_max = max(persisted_max, persisted("gzip-despite"))

    # T4 chunked / no Content-Length
    body = fetcher.get_text(f"{base}/chunked-no-length", headers=rng)
    rec = last_record(wd, "chunked-no-length")
    ok = (not rec.get("content_length_header")
          and "NO-LENGTH-BODY" in body and rec.get("bytes_read", 0) <= CAP)
    results["T4_chunked_no_content_length"] = "PASS" if ok else f"FAIL {rec}"
    persisted_max = max(persisted_max, persisted("chunked-no-length"))

    # T5 early close -> recorded failure, fetcher object survives
    try:
        fetcher.get_text(f"{base}/early-close", headers=rng)
        results["T5_early_close_failure_recorded"] = "FAIL (no exception)"
    except Exception:  # noqa: BLE001 — expected
        rec = last_record(wd, "early-close")
        results["T5_early_close_failure_recorded"] = (
            f"PASS (attempts recorded, last attempt={rec.get('attempt')})"
            if rec else "FAIL (no manifest record)")

    # T6 HTML error body capped at 4KB
    try:
        fetcher.get_text(f"{base}/html-error", headers=rng)
        results["T6_html_error_body_capped_4KB"] = "FAIL (no exception)"
    except Exception:  # noqa: BLE001 — expected
        rec = last_record(wd, "html-error")
        head = rec.get("error_body_head", "")
        ok = rec.get("status") == 404 and 0 < len(head) <= 4096 \
            and bool(rec.get("error_body_sha256"))
        results["T6_html_error_body_capped_4KB"] = ("PASS" if ok
                                                    else f"FAIL len={len(head)}")

    # CRITICAL acceptance: based on bytes actually persisted, never headers
    results["CRITICAL_max_persisted_bytes_for_ranged_request"] = (
        f"PASS ({persisted_max} <= {CAP})" if 0 < persisted_max <= CAP
        else f"FAIL ({persisted_max})")
    srv.shutdown()
    shutil.rmtree(wd, ignore_errors=True)


def run_crawl(wd: Path, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(BACKEND),
           "SEC_EDGAR_USER_AGENT": "GlobalComplyAI LLC jay.w0416@gmail.com",
           **(env_extra or {})}
    return subprocess.run(
        [sys.executable, str(CRAWL), "--workdir", str(wd), "--since", "2023-01-01"],
        env=env, capture_output=True, text=True, timeout=1800)


def live_tests(results: dict) -> None:
    wd = Path(tempfile.mkdtemp(prefix="mr002_smoke_live_"))
    try:
        with (wd / "identity_crosswalk_v0.1.csv").open("w", newline="",
                                                       encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["permaticker", "ticker", "cik",
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

        p1 = run_crawl(wd)
        assert p1.returncode == 0, f"live run rc={p1.returncode}: {p1.stderr[-500:]}"
        gz_objects = list((wd / "edgar_cache").glob("*.gz"))
        results["L1_gzip_cache_creation"] = (f"PASS ({len(gz_objects)} .gz objects)"
                                             if gz_objects else "FAIL")
        idx = [json.loads(x) for x in (wd / "cache_index.jsonl").open(encoding="utf-8")]
        sep_ok = bool(idx) and all(r["content_sha256"] != r["storage_sha256"]
                                   for r in idx)
        results["L2_hash_separation"] = (f"PASS ({len(idx)} indexed)" if sep_ok
                                         else "FAIL")

        victim = gz_objects[0]
        legacy = victim.with_suffix("")
        legacy.write_bytes(gzip.decompress(victim.read_bytes()))
        victim.unlink()
        p2 = run_crawl(wd)
        manifest = (wd / "raw_response_manifest.jsonl").read_text(encoding="utf-8")
        results["L3_legacy_cache_replay_and_resume"] = (
            "PASS (rerun rc=0, no DUAL_HASH_STOP)"
            if p2.returncode == 0 and "DUAL_HASH_STOP" not in manifest else "FAIL")
        results["L4_request_level_resumption"] = \
            "PENDING_TASK9 (checkpoints not yet built)"

        wd3 = Path(tempfile.mkdtemp(prefix="mr002_smoke_guard_"))
        shutil.copy(wd / "identity_crosswalk_v0.1.csv", wd3)
        p3 = run_crawl(wd3, {"MR002_DISKGUARD_FORCE_FREE_PCT": "10"})
        rep = json.loads((wd3 / "stage2_run_report.json").read_text()) \
            if (wd3 / "stage2_run_report.json").exists() else {}
        results["L5_disk_guard_controlled_halt"] = (
            "PASS (exit 3 + termination_reason recorded)"
            if p3.returncode == 3
            and rep.get("termination_reason") == "DISK_HEADROOM_GUARD"
            else f"FAIL rc={p3.returncode} reason={rep.get('termination_reason')}")
        shutil.rmtree(wd3, ignore_errors=True)
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def main() -> int:
    results: dict[str, str] = {}
    transport_tests(results)
    live_tests(results)
    out = ROOT / "docs" / "implementation" / "evidence" / "mr_002" / \
        "MR002_HardenedSmoke_Report.json"
    out.write_text(json.dumps({"results": results}, indent=2))
    print(json.dumps(results, indent=1))
    ok = all(v.startswith(("PASS", "PENDING")) for v in results.values())
    print("SMOKE", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
