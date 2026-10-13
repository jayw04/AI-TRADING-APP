"""Build the FROZEN sample manifest for the SIP trades probe from the stored minute bars.

READ-ONLY and return-blind: it reads only which minutes have a bar (timestamps) and the per-symbol
median daily bar volume (for a liquidity tercile). Prices are never selected. The selection is
deterministic (hash order with a fixed seed string), so the same store yields the same manifest.

    python -I build_trades_probe_manifest.py --store STORE.duckdb --out MANIFEST.json

Strata (frozen here, before any request):
  A  representative missing-09:30 symbol-days: liquidity tercile x month, N_PER_STRATUM each,
     excluding the two special dates;
  B  the two dates with market-wide gaps (2016-02-02, 2016-02-22): for each, SPECIAL_PER_DATE runs
     of missing regular-session minutes (the longest RUNS_LONGEST, the rest by hash order).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import time
from pathlib import Path

import duckdb

SEED = "RANGE002-TRADES-PROBE-v1"
N_PER_STRATUM = 2
SPECIAL_DATES = ("2016-02-02", "2016-02-22")
SPECIAL_PER_DATE = 6
RUNS_LONGEST = 3
MAX_INTERVAL_MIN = 5
CONTEXT_MIN = 3


def _h(*parts: str) -> str:
    return hashlib.sha256("|".join((SEED, *parts)).encode()).hexdigest()


def _hms(minute_of_day: int) -> str:
    return time(minute_of_day // 60, minute_of_day % 60).isoformat()


def build(store: Path) -> dict[str, object]:
    con = duckdb.connect(str(store), read_only=True)
    df = con.execute("select symbol, ts, volume from minute_bars").df()
    con.close()
    et = df["ts"].dt.tz_localize("UTC").dt.tz_convert("America/New_York").dt.tz_localize(None)
    df["day"] = et.dt.strftime("%Y-%m-%d")
    df["mod"] = et.dt.hour * 60 + et.dt.minute
    reg = df[(df["mod"] >= 570) & (df["mod"] <= 959)]
    present: dict[tuple[str, str], set[int]] = defaultdict(set)
    for sym, day, mod in zip(reg["symbol"], reg["day"], reg["mod"], strict=True):
        present[(sym, day)].add(int(mod))
    med = reg.groupby(["symbol", "day"])["volume"].sum().groupby("symbol").median()
    order = sorted(med.index, key=lambda s: (float(med[s]), s))
    third = len(order) / 3.0
    tercile = {s: min(int(i // third), 2) for i, s in enumerate(order)}

    samples: list[dict[str, str]] = []
    strata: dict[tuple[int, str], list[tuple[str, str]]] = defaultdict(list)
    for (sym, day), mods in present.items():
        if 570 not in mods and day not in SPECIAL_DATES:
            strata[(tercile[sym], day[:7])].append((sym, day))
    n = 0
    for key in sorted(strata):
        pool = sorted(strata[key], key=lambda sd: _h(*sd))
        for sym, day in pool[:N_PER_STRATUM]:
            n += 1
            samples.append(
                {
                    "id": f"A{n:02d}",
                    "stratum": f"missing_0930|liq_tercile={key[0]}|month={key[1]}",
                    "symbol": sym,
                    "day": day,
                    "interval_start_et": "09:30:00",
                    "interval_end_et": "09:31:00",
                    "window_start_et": "09:25:00",
                    "window_end_et": "09:36:00",
                }
            )
    for day in SPECIAL_DATES:
        runs: list[tuple[int, int, str]] = []  # (length, start_minute, symbol)
        for (sym, d), mods in present.items():
            if d != day:
                continue
            m = 570
            while m <= 959:
                if m in mods:
                    m += 1
                    continue
                start = m
                while m <= 959 and m not in mods:
                    m += 1
                runs.append((m - start, start, sym))
        longest = sorted(runs, key=lambda r: (-r[0], _h(day, r[2], str(r[1]))))[:RUNS_LONGEST]
        rest = [r for r in runs if r not in longest]
        rest.sort(key=lambda r: _h(day, r[2], str(r[1])))
        picked = longest + rest[: SPECIAL_PER_DATE - len(longest)]
        for k, (length, start, sym) in enumerate(picked, 1):
            span = min(length, MAX_INTERVAL_MIN)
            samples.append(
                {
                    "id": f"B{day[5:7]}{day[8:10]}-{k}",
                    "stratum": f"special_date={day}|run_len={length}",
                    "symbol": sym,
                    "day": day,
                    "interval_start_et": _hms(start),
                    "interval_end_et": _hms(start + span),
                    "window_start_et": _hms(max(570, start - CONTEXT_MIN)),
                    "window_end_et": _hms(min(960, start + span + CONTEXT_MIN)),
                }
            )
    return {
        "schema": "range002.trades_probe_manifest.v1",
        "seed": SEED,
        "selection": "return-blind: bar presence and per-symbol median daily bar volume only",
        "samples": samples,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--store", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    a = p.parse_args()
    if a.out.exists():
        raise SystemExit(f"{a.out} exists; never overwritten")
    doc = build(a.store)
    text = json.dumps(doc, indent=1, sort_keys=True) + "\n"
    a.out.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode()).hexdigest()
    print(f"wrote {a.out} samples={len(doc['samples'])} sha256={digest}")  # type: ignore[arg-type]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
