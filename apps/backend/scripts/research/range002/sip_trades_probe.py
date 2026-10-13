"""RANGE-002 RETURN-BLIND SIP trades probe for missing 1-minute bars (scoped diagnostic path).

    python -I sip_trades_probe.py --manifest M.json --manifest-sha256 H --max-requests 40 \\
        --key-env K --secret-env S --out OUT.json --access-log LOG.jsonl

Purpose: for a FROZEN list of (symbol, day, interval) whose 1-minute SIP bar is absent from the
stored bars, retrieve the SIP trades of the interval (plus a small context window) and report, per
sample, timestamps, counts, trade-condition codes and a classification. It is a data-quality
diagnostic: it computes no strategy performance and consumes no P3A attempt. The manifest is frozen
before any request: the tool refuses to run unless the manifest file's sha256 equals
``--manifest-sha256``.

RETURN-BLIND BY CONSTRUCTION: only each trade's timestamp ``t`` and condition codes ``c`` are read.
Price (``p``) and size (``s``) are never read into any variable, and the output schema has no field
for them.

Hard request cap (``--max-requests``, required) counts EVERY HTTP request including pagination and
429 retries. When the cap, an HTTP error or a truncated response prevents complete retrieval of the
interval, the sample is ``INCOMPLETE_EVIDENCE``; an empty or truncated response is never read as
"no trades". Classification vocabulary (assumptions are explicit and the raw condition histogram is
always reported so a reader can reclassify):

  NO_TRADES_RETURNED                 complete response, none in the interval, but trades returned in
                                     the surrounding window (a no-print minute as far as the
                                     provider's trades endpoint shows)
  TRADES_PRESENT_POTENTIALLY_EXCLUDED_BY_BAR_RULES
                                     trades in the interval and every one carries a condition code
                                     outside the assumed regular set (``@``, ``F``)
  ELIGIBLE_TRADES_PRESENT_BAR_ABSENT at least one trade in the interval carries only assumed
                                     regular codes while the bar is absent: an aggregation or
                                     delivery anomaly to investigate
  UNRESOLVED_AVAILABILITY            complete response, no trades in the interval nor in the whole
                                     window (halt, illiquidity or another availability cause; the
                                     trades endpoint cannot tell which)
  INCOMPLETE_EVIDENCE                see above
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from datetime import time as dtime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

BASE_URL = "https://data.alpaca.markets/v2/stocks"
_ET = ZoneInfo("America/New_York")
EXIT_OK, EXIT_REFUSED = 0, 2
TOOL_VERSION = "1.0.0"
PAGE_LIMIT = 10_000
MAX_REQUESTS_PER_SAMPLE = 4
#: ASSUMPTION, labelled as such: SIP condition codes treated as "regular" (regular sale, ISO sweep)
REGULAR_CONDITIONS = frozenset({"@", "F"})
MANIFEST_SCHEMA = "range002.trades_probe_manifest.v1"

CLASS_NO_TRADES = "NO_TRADES_RETURNED"
CLASS_EXCLUDED = "TRADES_PRESENT_POTENTIALLY_EXCLUDED_BY_BAR_RULES"
CLASS_ELIGIBLE = "ELIGIBLE_TRADES_PRESENT_BAR_ABSENT"
CLASS_UNRESOLVED = "UNRESOLVED_AVAILABILITY"
CLASS_INCOMPLETE = "INCOMPLETE_EVIDENCE"

RECORD_FIELDS = (
    "id",
    "stratum",
    "symbol",
    "day",
    "interval_et",
    "window_et",
    "http_status",
    "requests_used",
    "complete",
    "next_page_token_present",
    "trades_in_window_returned",
    "trades_in_interval",
    "trades_before_interval",
    "trades_after_interval",
    "first_in_interval_et",
    "last_in_interval_et",
    "last_returned_et",
    "condition_histogram_interval",
    "interval_trades_with_only_regular_codes",
    "classification",
)


class ProbeRefusal(RuntimeError):
    """The probe was not run or stopped; the message never contains a credential value."""


@dataclass(frozen=True)
class Sample:
    id: str
    stratum: str
    symbol: str
    day: date
    interval_start: dtime
    interval_end: dtime
    window_start: dtime
    window_end: dtime


HttpGet = Callable[[str, Mapping[str, str], Mapping[str, str]], tuple[int, Any]]


def _hms(text: str) -> dtime:
    return dtime.fromisoformat(text)


def load_manifest(path: Path, expected_sha256: str) -> tuple[list[Sample], str]:
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != expected_sha256:
        raise ProbeRefusal(f"manifest sha256 {sha} != the frozen {expected_sha256}; nothing sent")
    doc = json.loads(raw.decode("utf-8"))
    if doc.get("schema") != MANIFEST_SCHEMA or not isinstance(doc.get("samples"), list):
        raise ProbeRefusal("manifest schema is not range002.trades_probe_manifest.v1")
    out: list[Sample] = []
    seen: set[str] = set()
    for s in doc["samples"]:
        smp = Sample(
            id=str(s["id"]),
            stratum=str(s["stratum"]),
            symbol=str(s["symbol"]),
            day=date.fromisoformat(s["day"]),
            interval_start=_hms(s["interval_start_et"]),
            interval_end=_hms(s["interval_end_et"]),
            window_start=_hms(s["window_start_et"]),
            window_end=_hms(s["window_end_et"]),
        )
        if smp.id in seen:
            raise ProbeRefusal(f"duplicate sample id {smp.id}")
        seen.add(smp.id)
        if not (smp.window_start <= smp.interval_start < smp.interval_end <= smp.window_end):
            raise ProbeRefusal(f"{smp.id}: interval must lie inside its window")
        out.append(smp)
    if not out:
        raise ProbeRefusal("manifest has no samples")
    return out, sha


def _rfc3339(d: date, t: dtime) -> str:
    return datetime.combine(d, t, tzinfo=_ET).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(text: str) -> datetime:
    """Provider timestamps carry nanoseconds; keep microseconds. Aware UTC -> ET."""
    base, _, frac = text.rstrip("Z").partition(".")
    stamp = f"{base}.{frac[:6].ljust(6, '0')}" if frac else base
    return datetime.fromisoformat(stamp).replace(tzinfo=UTC).astimezone(_ET)


def classify(
    *,
    complete: bool,
    interval_codes: list[tuple[str, ...]],
    n_window: int,
) -> str:
    """Pure classification (frozen). ``interval_codes`` has one tuple of condition codes per trade
    in the interval; ``n_window`` is every trade returned for the whole window."""
    if not complete:
        return CLASS_INCOMPLETE
    if interval_codes:
        regular_only = [c for c in interval_codes if c and set(c) <= REGULAR_CONDITIONS]
        return CLASS_ELIGIBLE if regular_only else CLASS_EXCLUDED
    return CLASS_NO_TRADES if n_window > 0 else CLASS_UNRESOLVED


def _httpx_get(timeout_s: float) -> HttpGet:
    import httpx

    client = httpx.Client(timeout=timeout_s, follow_redirects=False)

    def get(url: str, params: Mapping[str, str], headers: Mapping[str, str]) -> tuple[int, Any]:
        try:
            resp = client.get(url, params=dict(params), headers=dict(headers))
        except httpx.HTTPError as exc:  # type name only: the message could echo request details
            raise ProbeRefusal(f"HTTP transport failure: {type(exc).__name__}") from None
        try:
            body: Any = resp.json()
        except ValueError:
            body = None
        return resp.status_code, body

    return get


class _Budget:
    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.used = 0

    def left(self) -> int:
        return self.cap - self.used


def _probe_one(
    smp: Sample,
    *,
    budget: _Budget,
    headers: Mapping[str, str],
    http_get: HttpGet,
    sleep: Callable[[float], None],
) -> dict[str, Any]:
    url = f"{BASE_URL}/{smp.symbol}/trades"
    params: dict[str, str] = {
        "feed": "sip",
        "start": _rfc3339(smp.day, smp.window_start),
        "end": _rfc3339(smp.day, smp.window_end),
        "limit": str(PAGE_LIMIT),
        "sort": "asc",
    }
    iv_lo = datetime.combine(smp.day, smp.interval_start, tzinfo=_ET)
    iv_hi = datetime.combine(smp.day, smp.interval_end, tzinfo=_ET)
    stamps: list[datetime] = []
    codes: list[tuple[str, ...]] = []
    status, used = 0, 0
    token_present = False
    complete = False
    error = False
    while True:
        body: Any = None
        for retry in range(3):
            if budget.left() <= 0 or used >= MAX_REQUESTS_PER_SAMPLE:
                error = True
                break
            budget.used += 1
            used += 1
            status, body = http_get(url, params, headers)
            if status != 429:
                break
            sleep(2.0 * (retry + 1))
        else:
            error = True
        if error:
            break
        if status != 200 or not isinstance(body, dict):
            error = True
            break
        trades = body.get("trades")
        if not isinstance(trades, list):
            error = True
            break
        for tr in trades:  # ONLY t and c are read; price and size are never touched
            if not isinstance(tr, dict) or not isinstance(tr.get("t"), str):
                error = True
                break
            stamps.append(_parse_ts(tr["t"]))
            c = tr.get("c")
            codes.append(tuple(x for x in c if isinstance(x, str)) if isinstance(c, list) else ())
        if error:
            break
        token = body.get("next_page_token")
        token_present = isinstance(token, str) and bool(token)
        if not token_present:
            complete = True  # no further pages: the whole window was returned
            break
        if stamps and max(stamps) >= iv_hi:
            complete = True  # ascending order: the interval is fully covered by what was returned
            break
        params = {**params, "page_token": str(token)}
    inside = [i for i, ts in enumerate(stamps) if iv_lo <= ts < iv_hi]
    in_codes = [codes[i] for i in inside]
    hist = Counter(code for i in inside for code in (codes[i] or ("<none>",)))
    cls = classify(complete=complete and not error, interval_codes=in_codes, n_window=len(stamps))
    rec: dict[str, Any] = {
        "id": smp.id,
        "stratum": smp.stratum,
        "symbol": smp.symbol,
        "day": smp.day.isoformat(),
        "interval_et": f"{smp.interval_start.isoformat()}-{smp.interval_end.isoformat()}",
        "window_et": f"{smp.window_start.isoformat()}-{smp.window_end.isoformat()}",
        "http_status": status,
        "requests_used": used,
        "complete": bool(complete and not error),
        "next_page_token_present": token_present,
        "trades_in_window_returned": len(stamps),
        "trades_in_interval": len(inside),
        "trades_before_interval": sum(1 for ts in stamps if ts < iv_lo),
        "trades_after_interval": sum(1 for ts in stamps if ts >= iv_hi),
        "first_in_interval_et": stamps[inside[0]].strftime("%H:%M:%S.%f") if inside else None,
        "last_in_interval_et": stamps[inside[-1]].strftime("%H:%M:%S.%f") if inside else None,
        "last_returned_et": max(stamps).strftime("%H:%M:%S.%f") if stamps else None,
        "condition_histogram_interval": dict(sorted(hist.items())),
        "interval_trades_with_only_regular_codes": sum(
            1 for c in in_codes if c and set(c) <= REGULAR_CONDITIONS
        ),
        "classification": cls,
    }
    assert tuple(rec) == RECORD_FIELDS
    return rec


def run_probe(
    samples: list[Sample],
    *,
    max_requests: int,
    key: str,
    secret: str,
    http_get: HttpGet,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if max_requests <= 0:
        raise ProbeRefusal("max-requests must be positive")
    if len(samples) > max_requests:
        raise ProbeRefusal(
            f"{len(samples)} samples exceed the hard cap of {max_requests} requests; nothing sent"
        )
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    budget = _Budget(max_requests)
    records = [
        _probe_one(s, budget=budget, headers=headers, http_get=http_get, sleep=sleep)
        for s in samples
    ]
    counts = Counter(r["classification"] for r in records)
    return {
        "schema": "range002.trades_probe.v1",
        "tool_version": TOOL_VERSION,
        "return_blind": True,
        "values_read": ["t", "c", "next_page_token(presence)"],
        "feed": "sip",
        "regular_condition_assumption": sorted(REGULAR_CONDITIONS),
        "requests_made": budget.used,
        "max_requests": max_requests,
        "executed_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "classification_counts": dict(sorted(counts.items())),
        "records": records,
        "interpretation": (
            "an empty or truncated response is never read as 'no trades'; NO_TRADES_RETURNED is "
            "only the provider's complete response for the interval. Halt and other availability "
            "causes are not observable from trades alone."
        ),
    }


def _append_access_log(path: Path, record: dict[str, Any]) -> None:
    prev = "0" * 64
    if path.exists():
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if lines:
            prev = hashlib.sha256(lines[-1].encode("utf-8")).hexdigest()
    line = json.dumps(dict(record, prev_line_sha256=prev), sort_keys=True, allow_nan=False)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(line + "\n")


def main(argv: list[str] | None = None, *, http_get: HttpGet | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--manifest-sha256", required=True)
    p.add_argument("--max-requests", required=True, type=int)
    p.add_argument("--key-env", required=True)
    p.add_argument("--secret-env", required=True)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--access-log", required=True, type=Path)
    a = p.parse_args(argv)
    try:
        if a.out.exists():
            raise ProbeRefusal(f"{a.out} already exists; never overwritten")
        if not a.out.parent.is_dir():
            raise ProbeRefusal(f"{a.out.parent} is not an existing directory")
        samples, manifest_sha = load_manifest(a.manifest, a.manifest_sha256)
        key, secret = os.environ.get(a.key_env), os.environ.get(a.secret_env)
        if not key or not secret:
            raise ProbeRefusal(
                f"environment variables {a.key_env} / {a.secret_env} are not both set"
            )
        _append_access_log(
            a.access_log,
            {
                "event": "trades_probe_start",
                "manifest_sha256": manifest_sha,
                "samples": len(samples),
                "max_requests": a.max_requests,
                "tool_version": TOOL_VERSION,
            },
        )
        out = run_probe(
            samples,
            max_requests=a.max_requests,
            key=key,
            secret=secret,
            http_get=http_get or _httpx_get(30.0),
        )
    except (ProbeRefusal, ValueError, KeyError) as exc:
        print(f"REFUSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    out["manifest_sha256"] = manifest_sha
    text = json.dumps(out, indent=2, sort_keys=True) + "\n"
    a.out.write_text(text, encoding="utf-8")
    try:  # PU-1: scope sidecar when the app package is importable (it is, in the bundle)
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from app.licensing.envelope import write_sidecar

        write_sidecar(a.out, ("alpaca_market_data",))
    except ImportError:
        pass
    _append_access_log(
        a.access_log,
        {
            "event": "trades_probe_done",
            "manifest_sha256": manifest_sha,
            "requests_made": out["requests_made"],
            "classification_counts": out["classification_counts"],
            "out_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        },
    )
    print(
        f"wrote {a.out}: {out['requests_made']} request(s), "
        f"{len(out['records'])} record(s), {out['classification_counts']}"
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())


#: a Mapping-typed alias keeps the HttpGet signature importable for tests
__all__ = ["HttpGet", "classify", "load_manifest", "main", "run_probe"]
