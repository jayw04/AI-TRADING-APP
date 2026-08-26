"""SEC-001 V3 — SUCCESSOR EPOCH: crawl identities 1..1,167 from 0/1,167.

Authorized by SUCCESSOR_EPOCH_0_1167 after Gates 1-5. A clean epoch: the v1.4 374 never
enter this count.

Orchestration only. The acquisition path (66247ad) is not modified: no change to
acquisition semantics, SIC interpretation, forms, response classification, ceilings, or
transport behaviour. Structure is the proven v1.4 controller (894e4744); the deltas are

  * fresh epoch rooted at /opt/epoch, starting at 0 terminal identities;
  * Gate-5 TerminalStorageReserve caught BY NAME at top level, before ordinary Exception
    handling -- never `except BaseException`, which would swallow KeyboardInterrupt and
    SystemExit;
  * physical 2 GiB reserve released on a controlled stop, so the terminal record can
    always be written. v1.4 died on ENOSPC and then could not write its own stop record;
  * atomic terminal write (temp -> flush -> fsync -> rename) so a partial or zero-byte
    stop file can never masquerade as a successful stop.

Unit-boundary credit only: an interrupted unit restarts from its governed unit boundary.
No partial-unit credit is invented here.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

CODE = "/opt/epoch/code2/apps/backend"
EPOCH_ROOT = Path("/opt/epoch/crawl-successor")
STATE_ROOT = EPOCH_ROOT / "state"
PROGRESS_LOG = EPOCH_ROOT / "runner_progress.jsonl"
STOP_FILE = EPOCH_ROOT / "RUNNER_STOPPED.json"
RESERVE = Path("/opt/epoch/TERMINAL_RESERVE.bin")

CIK_ARTIFACT = "/opt/epoch/manifest/SEC001_V3_CIK_RESOLUTION_V1.json"
CIK_SHA = "1f7d523b9419301a16d36234f19584266f3e61fc4e5673e589d0ba7016877146"
FROZEN_ORDER = "/opt/epoch/manifest/SEC001_V3_FROZEN_IDENTITY_ORDER.json"
FROZEN_ORDER_SHA = "e8445b0b6ea08bf1ff5ad5a08db6cc3797f5161fb53be3a0aed4b9b24c8f9c35"

sys.path.insert(0, "/opt/epoch/code2/site")
sys.path.insert(0, CODE)

from app.altdata.sec001_v3 import policy  # noqa: E402
from app.altdata.sec001_v3.driver import CrawlDriver, open_evidence_log  # noqa: E402
from app.altdata.sec001_v3.fetch import (  # noqa: E402
    CrawlHalt,
    PolicyFetcher,
    TerminalStorageReserve,
)
from app.altdata.sec001_v3.forbidden import FORBIDDEN_COVERAGE_FIELDS  # noqa: E402
from app.altdata.sec001_v3.spine import Spine  # noqa: E402
from app.altdata.sec001_v3.state import CrawlState, WorkUnit  # noqa: E402
import app.altdata.mr002.crosswalk as CW  # noqa: E402
import app.altdata.mr002.sic_history as SH  # noqa: E402

FROZEN_SPINE_BLOB = "48779adaaaecfeffb9c6a32be8531f784d72058a"


def _blob(path: str) -> str:
    d = Path(path).read_bytes()
    return hashlib.sha1(b"blob " + str(len(d)).encode() + bytes([0]) + d).hexdigest()


assert _blob(SH.__file__) == FROZEN_SPINE_BLOB, f"frozen spine changed: {SH.__file__}"

# ---- frozen identity order -----------------------------------------------------------
raw = Path(CIK_ARTIFACT).read_bytes()
assert hashlib.sha256(raw).hexdigest() == CIK_SHA, "CIK artifact digest mismatch"
art = json.loads(raw)

units = sorted({
    WorkUnit(cik=int(r["cik"]), ticker=str(r["tickers_source_row"]["ticker"]).upper(),
             permaticker=int(r["permaticker"]))
    for r in art["identities"] if r["status"] == "RESOLVED_CIK"
})
assert len(units) == 1167, f"expected 1167 units, got {len(units)}"

_fo = Path(FROZEN_ORDER).read_bytes()
assert hashlib.sha256(_fo).hexdigest() == FROZEN_ORDER_SHA, "frozen order digest mismatch"
_expected = [r["unit_key"] for r in json.loads(_fo)["identities"]]
assert [u.key for u in units] == _expected, "derived order != sealed frozen order"

EPOCH_ROOT.mkdir(parents=True, exist_ok=True)
STATE_ROOT.mkdir(parents=True, exist_ok=True)
state = CrawlState.load(STATE_ROOT)


def utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _atomic_write(path: Path, payload: bytes) -> None:
    """temp -> flush -> fsync -> rename. A partial write can never look like success."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    dfd = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def _flush_all() -> None:
    for p in (PROGRESS_LOG, STATE_ROOT / "crawl_progress.jsonl"):
        try:
            if p.exists():
                fd = os.open(str(p), os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        except OSError:
            pass
    os.sync()


def _release_reserve() -> dict:
    """Free the physical 2 GiB so the terminal record can always be written."""
    info = {"existed": RESERVE.exists(), "bytes": 0, "released": False}
    try:
        if RESERVE.exists():
            info["bytes"] = RESERVE.stat().st_size
            RESERVE.unlink()
            info["released"] = True
    except OSError as exc:
        info["error"] = str(exc)
    return info


def stop(reason: str, detail: object, *, release: bool = False, code: int = 2) -> None:
    rec = {"stopped_utc": utc(), "reason": reason, "detail": detail,
           "units_completed": len(state.done), "units_total": len(units),
           "epoch": "successor-0-1167"}
    if release:
        rec["reserve"] = _release_reserve()
    _atomic_write(STOP_FILE, (json.dumps(rec, indent=2, sort_keys=True) + "\n").encode())
    _flush_all()
    print("HARD STOP:", reason, json.dumps(detail)[:400], flush=True)
    sys.exit(code)


def check_unit(fetcher: PolicyFetcher, unit: WorkUnit) -> None:
    for acc, status in fetcher.header_status.items():
        if status == policy.ACQ_HEADER_INCOMPLETE:
            stop("ACQUISITION_HEADER_INCOMPLETE", {"accession": acc, "unit": unit.key})
        if status == policy.ACQ_ENCODING_UNSUPPORTED:
            stop("ACQUISITION_ENCODING_UNSUPPORTED", {"accession": acc, "unit": unit.key})
    for acc, d in fetcher.decisions.items():
        if d.parser_body_sha256 != d.sha256:
            stop("parser_body_sha256 != source_decision_bytes_sha256",
                 {"accession": acc, "unit": unit.key})
        if not d.artifact_path or not Path(d.artifact_path).exists():
            stop("decision-byte evidence missing", {"accession": acc, "unit": unit.key})
        enc = (d.response_content_encoding or "").strip().lower()
        if enc not in ("", "identity") and d.wire_sha256 == d.parser_body_sha256:
            stop("encoded body reached the parser undecoded",
                 {"accession": acc, "unit": unit.key, "encoding": enc})
        if any(a.range_header for a in d.attempts) and enc not in ("", "identity"):
            stop("ranged fallback returned an encoded representation",
                 {"accession": acc, "unit": unit.key, "encoding": enc})
        # Gate-5 era: bounded consumption is now an asserted runtime property.
        if d.attempts and any(
            getattr(a, "byte_length", 0) > policy.RESPONSE_CONSUMPTION_CEILING_BYTES
            for a in d.attempts
        ):
            stop("response consumption exceeded the governed ceiling",
                 {"accession": acc, "unit": unit.key})


def check_state_invariants(prev_terminal: int) -> int:
    lines = [x for x in (STATE_ROOT / "crawl_progress.jsonl").read_text().splitlines()
             if x.strip()]
    keys = [json.loads(x)["unit_key"] for x in lines]
    n = len(keys)
    if n < prev_terminal:
        stop("terminal count decreased", {"was": prev_terminal, "now": n})
    if len(set(keys)) != n:
        dupes = [k for k in set(keys) if keys.count(k) > 1]
        stop("duplicate terminal identity", {"duplicates": dupes[:5]})
    frozen = [u.key for u in units]
    if keys != frozen[:n]:
        first_bad = next((i for i, (a, b) in enumerate(zip(keys, frozen)) if a != b), n)
        stop("terminal identities are not a prefix of the frozen order",
             {"index": first_bad, "got": keys[first_bad] if first_bad < n else None,
              "expected": frozen[first_bad] if first_bad < len(frozen) else None})
    for x in lines:
        rec = json.loads(x)
        obs = EPOCH_ROOT / policy.RAW_PREFIX / "observations" / f"{rec['cik']:010d}.jsonl"
        if not obs.exists():
            stop("partial unit became terminal", {"unit": rec["unit_key"], "missing": str(obs)})
    return n


def check_global(fetcher: PolicyFetcher) -> None:
    path = EPOCH_ROOT / policy.RAW_PREFIX / "source_evidence.jsonl"
    if not path.exists():
        return
    stamps = []
    with path.open("rb") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            host = r["uri"].split("/")[2]
            if host not in ("www.sec.gov", "data.sec.gov"):
                stop("unexpected domain", {"host": host, "uri": r["uri"]})
            if r["method"] != "GET":
                stop("unexpected HTTP method", {"method": r["method"]})
            if r.get("form") and r["form"] not in policy.FORMS:
                stop("unexpected filing form", {"form": r["form"]})
            s = r.get("sent_monotonic_ns")
            if s is not None:
                stamps.append(s)
    stamps.sort()
    bad = [(stamps[i + 1] - stamps[i]) / 1e9 for i in range(len(stamps) - 1)
           if (stamps[i + 1] - stamps[i]) / 1e9 < 0.196]
    if bad:
        stop("actual-send rate proof violated", {"gaps_below_min": bad[:5]})


spine = Spine(sic_history=SH, crosswalk=CW, frozen_root=Path(CODE) / "app/altdata/mr002")
fetcher = PolicyFetcher(
    evidence=open_evidence_log(EPOCH_ROOT),
    decision_dir=EPOCH_ROOT / policy.RAW_PREFIX / "source_decision_bytes",
    sic_pattern=SH.SIC_RE,
)
drv = CrawlDriver(spine=spine, out_root=EPOCH_ROOT, fetcher=fetcher, state=state)

prev_terminal = len(state.done)
started = time.monotonic()
print(f"[{utc()}] successor epoch: {len(state.done)} terminal, "
      f"{len(units) - len(state.done)} pending of {len(units)}", flush=True)
print(f"[{utc()}] reserve present={RESERVE.exists()} "
      f"required_free={policy.PREARTIFACT_FREE_REQUIRED_BYTES}", flush=True)

try:
    while True:
        pending = state.pending(units)
        if not pending:
            break
        unit = pending[0]
        fetcher.header_status.clear()
        fetcher.decisions.clear()
        before = fetcher.requests_issued
        drv.run(units, limit=1)
        check_unit(fetcher, unit)
        prev_terminal = check_state_invariants(prev_terminal)

        done = len(state.done)
        elapsed = time.monotonic() - started
        rate = fetcher.requests_issued / elapsed if elapsed else 0
        rec = {"utc": utc(), "unit": unit.key, "done": done, "total": len(units),
               "requests_total": fetcher.requests_issued,
               "requests_this_unit": fetcher.requests_issued - before,
               "retries": fetcher.retries, "req_per_sec": round(rate, 3)}
        with PROGRESS_LOG.open("ab") as fh:
            fh.write((json.dumps(rec) + "\n").encode())
        if done % 25 == 0:
            check_global(fetcher)
            print(f"[{utc()}] {done}/{len(units)}  requests={fetcher.requests_issued} "
                  f"rate={rate:.2f}/s", flush=True)

# Gate 5: BY NAME, and before ordinary Exception handling. Never `except BaseException`.
except TerminalStorageReserve as r:
    stop("TERMINAL_STORAGE_RESERVE",
         {"free_bytes": r.free, "required_bytes": r.required, "path": r.path,
          "terminal_reserve_bytes": policy.TERMINAL_RESERVE_BYTES,
          "max_next_artifact_footprint": policy.MAX_NEXT_ARTIFACT_FOOTPRINT,
          "metadata_allowance_bytes": policy.METADATA_ALLOWANCE_BYTES,
          "controlled_stop": True},
         release=True, code=3)
except CrawlHalt as h:
    stop("CRAWL_HALT_403", {"status": h.status, "uri": h.uri})
except Exception as exc:  # noqa: BLE001
    stop("RUNNER_EXCEPTION", {"type": type(exc).__name__, "error": str(exc)[:300]})

check_global(fetcher)
blob = "".join(p.read_text(errors="replace") for p in EPOCH_ROOT.rglob("*.json*"))
hits = [f for f in FORBIDDEN_COVERAGE_FIELDS if '"' + f + '"' in blob]
if hits:
    stop("forbidden coverage field emitted", {"fields": hits})

final_keys = [json.loads(x)["unit_key"]
              for x in (STATE_ROOT / "crawl_progress.jsonl").read_text().splitlines()
              if x.strip()]
frozen_keys = [u.key for u in units]
if len(final_keys) != 1167:
    stop("completion: terminal count != 1167", {"count": len(final_keys)})
if len(set(final_keys)) != 1167:
    stop("completion: terminal identities are not unique",
         {"unique": len(set(final_keys)), "total": len(final_keys)})
if final_keys != frozen_keys:
    stop("completion: terminal identities are not the frozen order", {"mismatch": True})

_atomic_write(EPOCH_ROOT / "EPOCH_COMPLETE.json",
              (json.dumps({"completed_utc": utc(), "terminal_identities": 1167,
                           "requests": fetcher.requests_issued,
                           "retries": fetcher.retries}, indent=2, sort_keys=True) + "\n").encode())
_flush_all()
print(f"[{utc()}] SUCCESSOR EPOCH COMPLETE: 1167 unique terminal identities in frozen "
      f"order, {fetcher.requests_issued} requests, {fetcher.retries} retries", flush=True)
fetcher.close()
