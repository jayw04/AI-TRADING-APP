"""SEC-001 V3.1 — WP0A-Q-COVER step 1: bounded index-only ENVELOPE DERIVATION.

Authority: WP0A-Q-COVER (owner 2026-08-26), sub-authority of WP0A only. Governed by the
sealed pre-acquisition manifest

    manifests/wp0aq/WP0AQ_COVER_PREACQUISITION_MANIFEST_V1.json
    sha256 3a30ad0296aa945f6b7a68c2bf578e47c69f75267670c2e3d0e72d4473339724

This module performs **index enumeration only**. It issues SEC *index* requests against the
manifest's ``max_index_requests`` budget and issues **zero document requests**. It does not
fetch, open, parse or inspect any filing document, and it therefore produces no cover-page
observation and no security->CIK binding. Its single output is the frozen request envelope,
which the owner checks against planned scope *before* document acquisition is permitted
(manifest ``envelope_derivation_rule``; design v1.5 section 24.5 "Envelope", section 24.9).

Three controls are load-bearing and are the reason this is a separate module.

**Index responses are scope metadata, never security-binding evidence.** The EDGAR
``submissions`` document carries ``sic``, ``sicDescription``, ``tickers``, ``exchanges`` and
``name`` in its header region. The manifest's ``sic_blind`` prohibition and the operator's
standing instruction forbid extracting, exposing, writing, aggregating or inspecting any of
them. This module therefore projects each response down to four fields the instant it is
parsed -- ``cik``, ``form``, ``accession``, ``accepted_at`` -- and never retains, logs or
serialises the raw body. Those four are a strict subset of the manifest's
``retained_field_schema``, so the emitted envelope cannot carry a symbol, a class title, an
exchange, a sector or a SIC even in principle.

``primaryDocument`` is deliberately **excluded** although it would be convenient at
acquisition time: EDGAR primary-document filenames routinely embed the trading symbol
(``goog-20250630.htm``), which would smuggle a symbol into a scope artifact. The document
path is re-derived from the accession during acquisition, where symbol information is
in-scope.

**The identity-scope guard fails closed.** Before the envelope is written, every emitted
record is checked against the allowed key set and the whole serialised artifact is scanned
for forbidden field names. Either check failing aborts without writing.

**Acceptance-time semantics are measured, not assumed.** EDGAR stamps
``acceptanceDateTime`` with a ``Z`` suffix, but EDGAR acceptance timestamps are Eastern.
Rather than silently pick a reading, this module evaluates the manifest cutoff under *both*
and reports the difference. If the two agree the ambiguity is moot and needs no ruling; if
they disagree the disagreement is the finding, and the conservative (Eastern) reading
governs the primary envelope because it can only *exclude* filings.

Run:

    python scripts/sec001_v31_wp0aq_envelope.py [--out <path>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

try:  # ADR 0017 — outbound TLS rides the OS trust store (Norton SSL inspection).
    import truststore

    truststore.inject_into_ssl()
except Exception:  # pragma: no cover - truststore is present in the backend venv
    pass

REPO = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPO / "manifests" / "wp0aq" / "WP0AQ_COVER_PREACQUISITION_MANIFEST_V1.json"
MANIFEST_SHA256 = "3a30ad0296aa945f6b7a68c2bf578e47c69f75267670c2e3d0e72d4473339724"
DESIGN_COMMIT = "741445fd7830b27ede675def54c789435c256658"

USER_AGENT = "TradingWorkbench SEC001-V3 (GlobalComplyAI, LLC) jay.w0416@gmail.com"
SUBMISSIONS = "https://data.sec.gov/submissions/{name}"

#: Shard-selection floor. The envelope needs, per CIK, the latest permitted filing accepted
#: *before* the union window opens (2021-02-08) so that an inward-bounded binding can cover
#: the earliest rebalance at all. An annual-only filer (20-F/40-F) can have its last
#: pre-window periodic report as early as mid-2019, so shards are pulled back to 2019-01-01.
#: This costs at most one extra index request per CIK and never affects the document budget.
SHARD_FLOOR = "2019-01-01"

#: The only keys any emitted envelope record may carry. Strict subset of the manifest's
#: ``retained_field_schema``.
ALLOWED_RECORD_KEYS = frozenset({"cik", "form", "accession", "accepted_at"})

#: Field names whose presence anywhere in the serialised envelope means the SIC-blind /
#: identity-scope guard has been breached.
FORBIDDEN_TOKENS = (
    "sic",
    "sicDescription",
    "sic_description",
    "tickers",
    "ticker",
    "exchanges",
    "exchange",
    "stateOfIncorporation",
    "category",
    "primaryDocument",
    "primaryDocDescription",
    "entityType",
    "ein",
    "sector",
    "gics",
    "price",
    "return",
    "pnl",
)

ET = timezone(timedelta(hours=-4))  # EDGAR acceptance stamps are Eastern; EDT in this range.


class Halt(BaseException):
    """SEC returned a halt status. Enumeration stops; a human resumes it."""


class Budget(RuntimeError):
    """A frozen manifest cap would be exceeded."""


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class IndexFetcher:
    """Bounded, throttled, GET-only index fetcher under the sealed transport controls."""

    def __init__(self, m: dict[str, Any]) -> None:
        acq = m["acquisition"]
        self.max_requests = int(acq["max_index_requests"])
        self.max_retries = int(acq["max_total_retries"])
        self.retry_attempts = int(acq["retry_max_attempts"])
        self.retry_statuses = set(acq["retry_statuses"])
        self.halt_statuses = set(acq["halt_statuses"])
        self.ceiling = int(acq["response_consumption_ceiling_bytes"])
        self.stop_threshold = int(acq["consumption_stop_threshold_bytes"])
        self._interval = 1.0 / float(acq["rate_limit_per_sec"])
        self._last = 0.0
        self.requests = 0
        self.retries = 0
        self.log: list[dict[str, Any]] = []
        self._rng = random.Random("WP0AQ_COVER_ENVELOPE_V1")
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
            timeout=30.0,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def _throttle(self) -> None:
        gap = time.monotonic() - self._last
        if gap < self._interval:
            time.sleep(self._interval - gap)
        self._last = time.monotonic()

    def get_json(self, name: str) -> dict[str, Any] | None:
        """Fetch one submissions index document, bounded. ``None`` == fails closed."""
        url = SUBMISSIONS.format(name=name)
        for attempt in range(1, self.retry_attempts + 1):
            if self.requests >= self.max_requests:
                raise Budget(f"max_index_requests={self.max_requests} reached before {name}")
            self._throttle()
            self.requests += 1
            try:
                with self._client.stream("GET", url) as r:
                    status = r.status_code
                    if status in self.halt_statuses:
                        self.log.append(
                            {"name": name, "attempt": attempt, "status": status, "outcome": "HALT"}
                        )
                        raise Halt(f"EDGAR returned {status} for {url}")
                    if status in self.retry_statuses:
                        self.log.append(
                            {"name": name, "attempt": attempt, "status": status, "outcome": "RETRY"}
                        )
                        self.retries += 1
                        if self.retries > self.max_retries or attempt == self.retry_attempts:
                            return None
                        base = min(60.0, 1.0 * (2 ** (attempt - 1)))
                        time.sleep(base * (1.0 + self._rng.uniform(-0.25, 0.25)))
                        continue
                    if status != 200:
                        self.log.append(
                            {
                                "name": name,
                                "attempt": attempt,
                                "status": status,
                                "outcome": "FAIL_CLOSED_STATUS",
                            }
                        )
                        return None
                    # Bounded stream. Never materialise-then-slice; abort past the ceiling.
                    buf = bytearray()
                    over = False
                    for chunk in r.iter_bytes(65536):
                        buf.extend(chunk)
                        if len(buf) > self.ceiling:
                            over = True
                            break
                    if over:
                        self.log.append(
                            {
                                "name": name,
                                "attempt": attempt,
                                "status": 200,
                                "outcome": "FAIL_CLOSED_CEILING",
                                "bytes_seen": len(buf),
                            }
                        )
                        return None
                    nbytes = len(buf)
                    doc = json.loads(buf.decode("utf-8"))
                    del buf
                    self.log.append(
                        {
                            "name": name,
                            "attempt": attempt,
                            "status": 200,
                            "outcome": "OK",
                            "decoded_bytes": nbytes,
                            "over_stop_threshold": nbytes > self.stop_threshold,
                        }
                    )
                    return doc
            except Halt:
                raise
            except (httpx.HTTPError, ValueError, UnicodeDecodeError) as exc:
                self.log.append(
                    {
                        "name": name,
                        "attempt": attempt,
                        "outcome": "TRANSPORT_ERROR",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                self.retries += 1
                if self.retries > self.max_retries or attempt == self.retry_attempts:
                    return None
                base = min(60.0, 1.0 * (2 ** (attempt - 1)))
                time.sleep(base * (1.0 + self._rng.uniform(-0.25, 0.25)))
        return None


def project(cik: int, block: dict[str, Any]) -> list[dict[str, Any]]:
    """Project one filings block down to the four permitted scope fields.

    Everything else in the response -- SIC, tickers, exchanges, registrant name, document
    filenames -- is never read out of the parsed object and never leaves this function.
    """
    forms = block.get("form") or []
    accs = block.get("accessionNumber") or []
    acc_dt = block.get("acceptanceDateTime") or []
    fdates = block.get("filingDate") or []
    n = min(len(forms), len(accs), len(acc_dt), len(fdates))
    return [
        {
            "cik": cik,
            "form": forms[i],
            "accession": accs[i],
            "accepted_at": acc_dt[i],
            "_filing_date": fdates[i],
        }
        for i in range(n)
    ]


def parse_stamp(s: str) -> tuple[datetime, datetime]:
    """Return (literal-UTC reading, Eastern reading) of an EDGAR acceptance stamp."""
    t = s.replace("Z", "").replace("z", "").strip()
    if not t:
        raise ValueError("empty acceptance stamp")
    dt = datetime.fromisoformat(t)
    return dt.replace(tzinfo=UTC), dt.replace(tzinfo=ET).astimezone(UTC)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out", default=str(REPO / "artifacts" / "wp0aq" / "WP0AQ_COVER_ENVELOPE_V1.json")
    )
    args = ap.parse_args()
    out = Path(args.out)

    # --- CREATE-ONCE (manifest: immutable_artifact_identity) --------------------------
    if out.exists():
        print(f"REFUSING: {out} already exists (CREATE-ONCE).", file=sys.stderr)
        return 2

    # --- re-verify manifest identity BEFORE request #1 --------------------------------
    got = sha256_file(MANIFEST_PATH)
    if got != MANIFEST_SHA256:
        print(
            f"MANIFEST SHA MISMATCH\n  expected {MANIFEST_SHA256}\n  got      {got}",
            file=sys.stderr,
        )
        return 2
    m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if int(m["sec_requests_issued_by_this_manifest"]) != 0:
        print("MANIFEST STATE: requests already issued; refusing to re-derive.", file=sys.stderr)
        return 2
    print(f"manifest sha256 VERIFIED {got}")

    permitted = set(m["permitted_forms"])
    aliases = set(m["form_alias_universe"]["G0_FORM_ALIAS_CANDIDATES_V1"])
    cutoff_s = m["WP0A_Q_EVIDENCE_CUTOFF_UTC"]
    cutoff = datetime.fromisoformat(cutoff_s.replace("Z", "+00:00"))
    win_first = datetime.fromisoformat(m["union_window"]["first"]).replace(tzinfo=UTC)

    # --- unique CIKs in the frozen deterministic order --------------------------------
    pop = sorted(
        m["candidate_population"], key=lambda r: (-r["cells_in_union_window"], r["permaticker"])
    )
    order: list[int] = []
    cik_members: dict[int, list[int]] = {}
    for r in pop:
        c = int(r["v3_cik"])
        if c not in cik_members:
            cik_members[c] = []
            order.append(c)
        cik_members[c].append(int(r["permaticker"]))
    print(f"population {len(pop)} securities -> {len(order)} unique CIKs (CIK-once)")

    f = IndexFetcher(m)
    rows: list[dict[str, Any]] = []
    per_cik_status: dict[int, str] = {}
    try:
        for cik in order:
            name = f"CIK{cik:010d}.json"
            doc = f.get_json(name)
            if doc is None:
                per_cik_status[cik] = "INDEX_UNAVAILABLE"
                continue
            filings = doc.get("filings") or {}
            got_rows = project(cik, filings.get("recent") or {})
            shards = list(filings.get("files") or [])
            del doc
            # Pull older shards only if `recent` does not reach the shard floor.
            oldest = min((r["_filing_date"] for r in got_rows), default="9999-99-99")
            if oldest > SHARD_FLOOR:
                for sh in shards:
                    if str(sh.get("filingTo", "")) >= SHARD_FLOOR:
                        sdoc = f.get_json(str(sh["name"]))
                        if sdoc is None:
                            per_cik_status[cik] = "SHARD_UNAVAILABLE"
                            continue
                        got_rows.extend(project(cik, sdoc))
                        del sdoc
            rows.extend(got_rows)
            per_cik_status.setdefault(cik, "OK")
            n_perm = sum(1 for r in got_rows if r["form"] in permitted)
            print(
                f"  CIK {cik:>10}  filings_seen={len(got_rows):>5}  permitted_forms={n_perm:>4}"
                f"  [{per_cik_status[cik]}]  req={f.requests}"
            )
    except Halt as h:
        print(f"HALTED: {h}", file=sys.stderr)
        f.close()
        return 3
    except Budget as b:
        print(f"BUDGET: {b}", file=sys.stderr)
        f.close()
        return 3
    finally:
        f.close()

    # --- eligibility ------------------------------------------------------------------
    permitted_rows = [r for r in rows if r["form"] in permitted]
    alias_seen = sorted({r["form"] for r in rows if r["form"] in aliases})

    def eligible(reading: int) -> list[dict[str, Any]]:
        """reading 0 = literal-UTC stamp; 1 = Eastern stamp converted to UTC."""
        keep = []
        for r in permitted_rows:
            try:
                stamps = parse_stamp(r["accepted_at"])
            except ValueError:
                continue
            if stamps[reading] <= cutoff:
                keep.append(r)
        return keep

    def dedupe(rs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[int, str, str]] = set()
        outr: list[dict[str, Any]] = []
        for r in sorted(rs, key=lambda x: (x["cik"], x["accepted_at"], x["accession"])):
            k = (r["cik"], r["form"], r["accession"])
            if k in seen:
                continue
            seen.add(k)
            outr.append(
                {
                    "cik": r["cik"],
                    "form": r["form"],
                    "accession": r["accession"],
                    "accepted_at": r["accepted_at"],
                }
            )
        return outr

    elig_utc, elig_et = dedupe(eligible(0)), dedupe(eligible(1))
    primary = elig_et  # conservative reading governs; it can only exclude.

    env_a = [r for r in primary if parse_stamp(r["accepted_at"])[1] >= win_first]
    # Envelope B = A + per-CIK latest permitted filing accepted strictly BEFORE the window.
    bracket: list[dict[str, Any]] = []
    for cik in order:
        before = [
            r for r in primary if r["cik"] == cik and parse_stamp(r["accepted_at"])[1] < win_first
        ]
        if before:
            bracket.append(max(before, key=lambda x: parse_stamp(x["accepted_at"])[1]))
    env_b = dedupe(env_a + bracket)

    def summarise(rs: list[dict[str, Any]], label: str) -> dict[str, Any]:
        by_form: dict[str, int] = {}
        by_cik: dict[str, int] = {}
        for r in rs:
            by_form[r["form"]] = by_form.get(r["form"], 0) + 1
            by_cik[str(r["cik"])] = by_cik.get(str(r["cik"]), 0) + 1
        stamps = sorted(parse_stamp(r["accepted_at"])[1] for r in rs)
        return {
            "label": label,
            "total_eligible_accessions": len(rs),
            "unique_ciks_with_filings": len(by_cik),
            "filings_by_form": dict(sorted(by_form.items())),
            "filings_by_cik": by_cik,
            "ciks_with_zero_eligible": [c for c in order if str(c) not in by_cik],
            "earliest_accepted_utc": stamps[0].isoformat().replace("+00:00", "Z")
            if stamps
            else None,
            "latest_accepted_utc": stamps[-1].isoformat().replace("+00:00", "Z")
            if stamps
            else None,
        }

    envelope = {
        "artifact": "WP0AQ_COVER_ENVELOPE_V1",
        "authority": m["authority"],
        "manifest_sha256": MANIFEST_SHA256,
        "design_commit": DESIGN_COMMIT,
        "derived_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "phase": "INDEX_ONLY_ENVELOPE_DERIVATION",
        "document_requests_issued": 0,
        "cover_page_observations": 0,
        "index_requests_issued": f.requests,
        "index_request_cap": f.max_requests,
        "index_retries": f.retries,
        "evidence_cutoff_utc": cutoff_s,
        "permitted_forms": sorted(permitted),
        "form_aliases_observed": alias_seen,
        "population_securities": len(pop),
        "unique_ciks": len(order),
        "cik_order": order,
        "cik_to_permatickers": {str(k): v for k, v in cik_members.items()},
        "per_cik_index_status": {str(k): v for k, v in per_cik_status.items()},
        "acceptance_stamp_reading": {
            "note": (
                "EDGAR stamps acceptanceDateTime with a Z suffix but the clock is Eastern. "
                "Both readings are evaluated; the conservative Eastern reading governs."
            ),
            "eligible_under_literal_utc": len(elig_utc),
            "eligible_under_eastern": len(elig_et),
            "boundary_sensitivity": len(elig_utc) - len(elig_et),
        },
        "envelope_A_union_window": summarise(
            env_a, "A: accepted within union window [first, cutoff]"
        ),
        "envelope_B_with_left_bracket": summarise(
            env_b, "B: A + per-CIK latest permitted filing accepted before the union window"
        ),
        "planning_estimate_not_authority": m["planning_estimate_not_authority"],
        "max_document_requests": m["acquisition"]["max_document_requests"],
        "acquisition_keys_envelope_A": env_a,
        "acquisition_keys_envelope_B": env_b,
        "index_request_log": f.log,
    }

    # --- identity-scope guard: FAIL CLOSED -------------------------------------------
    for r in env_a + env_b:
        if set(r) - ALLOWED_RECORD_KEYS:
            print(f"IDENTITY-SCOPE GUARD FAILED: record keys {sorted(set(r))}", file=sys.stderr)
            return 2
    blob = json.dumps(envelope, indent=2, sort_keys=True)
    low = blob.lower()
    for tok in FORBIDDEN_TOKENS:
        if '"' + tok.lower() + '"' in low:
            print(
                f"SIC-BLIND GUARD FAILED: forbidden field name {tok!r} in envelope", file=sys.stderr
            )
            return 2
    print("identity-scope guard PASS · sic-blind guard PASS")

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(blob, encoding="utf-8")
    tmp.replace(out)
    print(f"\nwrote {out}")
    print(f"  sha256 {sha256_file(out)}")
    print(
        f"\nENVELOPE A  {envelope['envelope_A_union_window']['total_eligible_accessions']} filings"
    )
    print(
        f"ENVELOPE B  {envelope['envelope_B_with_left_bracket']['total_eligible_accessions']} filings"
    )
    print(f"index requests {f.requests}/{f.max_requests}   retries {f.retries}   documents 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
