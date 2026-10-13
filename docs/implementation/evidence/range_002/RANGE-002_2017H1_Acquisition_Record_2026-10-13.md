# RANGE-002 2017-H1 acquisition record (2026-10-13)

Private to Jay (PU-1 / PU-2). Authorised by the owner's instruction of 2026-10-13 (Lane C:
bounded personal-research acquisition; no strategy run is authorised by this record).

## Scope (fixed before any request)
| Item | Value |
|---|---|
| Evaluation window the data serves | 2017-01-01 .. 2017-06-30 (development_selection partition; not P3B) |
| Sharadar tables | TICKERS (all `table` values), ACTIONS (all dates), SEP with `date` in 2016-11-01 .. 2017-06-30 inclusive |
| Sharadar caps | `--max-pages 500` per table (fail closed) |
| SIP minute bars | raw, feed sip, 1Min, regular + extended hours as in the Q1 acquisition, monthly windows 2017-01..2017-06 |
| SIP symbols | the generated monthly top-100 universe union (domestic common, primary class), dated request symbols from the verified mapping |
| SIP HARD request cap | **2,500 in total**, including mapping probes, pagination and retries (not raised) |
| Estimate (provisional) | about 950 requests: 6 windows x about 150 symbols, plus probes and pagination |
| Lookback | 45 calendar days before 2017-01-01 (first SEP date must be <= 2016-11-17) |
| Credentials | read from the backend container environment, passed by name, never printed or stored |

## Basis (recorded, not verified)
Personal research on the owner's personal AWS account; provider terms apply; licence status
UNKNOWN for Sharadar and PERSONAL for Alpaca data; no presentation or redistribution.
Reused: the verified Q1 request-symbol construction (dated symbols, `asof` per segment policy).

## Path
1. Sharadar pull (single export). 2. Snapshot manifest. 3. Universe generation. 4. Dated symbol
mapping + return-blind probes. 5. SIP acquisition + validation in phase ACQ (consumes no attempt).
6. Only if every prerequisite passes (coverage, OR completeness >= 0.98, lookback, no
UNVERIFIED mapping, price consistency, PIT_FULL scope): one revised evaluation of E1 + E2a with
theta 0.10 using attempt 5, development-partition evidence. Otherwise the diagnostic is reported
and no attempt is opened. No threshold is lowered and no missing minute is reinterpreted.
