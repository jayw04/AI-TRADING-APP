# ADR0043-PROD-FACTOR-REFRESH-RECOVERY-001 — EFFECTIVENESS RECORD

> ## DECISION: **EFFECTIVE** — paper-box factor-refresh recovery only
>
> `ADR0043-PROD-FACTOR-REFRESH-RECOVERY-001` is approved and made effective for restoring the
> production factor-refresh producer on the paper box.
>
> ⛔ Grants **no** broker order authority, no strategy status change, no WS5 change, and no
> database migration.

## 1. Effective authorization

```
document_id                ADR0043-PROD-FACTOR-REFRESH-RECOVERY-001
document_pr                #614
approved_pr_head           3632be009e0c688601ea66a7c737e62fe9b88fbe
approved_document_blob     e0f3c38c312bc5ca9e274ba3e0e2f4bea3d72995
approved_canonical_sha256  0baa3e55bfc10db835ea2a42a955f17e56afad16e5bfc3720405704c429a3acc

effective_at               2026-08-05T00:00:00Z
expiration_at              2026-08-10T13:00:00Z
                           = EARLIER OF (effective_at + 168 h = 2026-08-12T00:00:00Z)
                                    AND (fixed deadline 2026-08-10T13:00:00Z)
                           the fixed deadline governs — 84 minutes before strategy 7
                           dispatches at 2026-08-10 10:24 ET

terminal_success           PRODUCTION_REFRESH_RECOVERED
terminal_failure           PRODUCTION_REFRESH_RECOVERY_FAILED
```

Any change to the approved document, its head, canonical body, the pinned implementation commit,
the three deployed-file digests, the production host identity, the provider binding or the
credential binding **invalidates this record** and requires a new review.

## 2. Scope

```
production host   i-084f47fe4e69192e9   (paper box)   application /opt/workbench/app
store             /opt/workbench/data/factor_data.duckdb
pre-recovery      sha256 13d74f51e52ea1cb15d83c6e22fef25f0566ed79a9180e95492f16c41a277580
provider          Nasdaq Data Link / Sharadar · SEP TICKERS ACTIONS · GET only
credential        NASDAQ_DATA_LINK_API_KEY   fingerprint 753417c970e0
units             workbench-factor-refresh.timer / .service   Mon-Fri 06:00 America/New_York
strategies        7 sector-rotation · 8 low-volatility        NOT disabled (§15 ruling)
```

**Authorized:** deploy the three pinned files · syntax and config validation · exactly one bounded
manual refresh · verification · atomic promotion · enable the refresh timer · observe one
execution · confirm strategies read the new sealed generation.

**Prohibited:** broker order activity · strategy execution or status changes · account mapping
changes · WS5 changes · database migrations · IAM expansion · instance resize · production image
rebuild · activation manifests.

## 3. Pinned implementation

```
implementation merge commit        d5d30d9000f8923c9712d0a25758195d1241dc8c   (PR #617)
apps/backend/scripts/factor_refresh.py
  b8b7f0395e7f6d6bbf71fff3ecab5fa483355e422441a97e3f856c9a33ed55a3
deploy/aws/docker-compose.factor-refresh.yml
  afa95eae542df21e733a79702868d4ce9eb38c47a8daa19d8a4b8dd49c3b2115
deploy/aws/factor-refresh.sh
  b5c13624e7bb9300e8015c1eef819c7c388bd4c0921e8359f9b7108821e0ab74
  supersedes deployed a199e855f0db74cf700209c127a96553c41c3e9f37f202252d633f2297233881
```

⚠ `factor-refresh.sh` must be deployed at **`b5c13624…`**, not the `bc32ab6c…` recorded in §1 of
the authorization. That value predates #617's `COMPOSE_REFRESH` and would reintroduce the exact
failure this recovery exists to fix.

## 4. Numeric limits

```
maximum runtime            60 min      maximum provider rows      900,000
maximum provider requests  3,000       ticker universe ceiling    2,000
minimum free disk retained 4 GiB       maximum staging size       500 MiB
concurrency                1           timer disabled during the manual run
```

## 5. Promotion gate

Promotion only when **all** hold: refresh exit code 0 · universe artifact integrity PASS · growth
control PASS · per-name coverage PASS · `lastpricedate` gate PASS · duplicate symbol rows 0 ·
provider ceiling respected · no unexplained universe member · no registered or held member omitted.

The sealed artifact advances only after verification passes, the swap succeeds, and the promoted
store is reopened and verified. A failed attempt must never replace the sealed anchor.

## 6. Dispatch protection

```
DISABLEMENT OF STRATEGIES 7 / 8   NOT REQUIRED (owner ruling)
BASIS                             recovery completes before the 2026-08-10 dispatch
```

⚠ The consuming interlock remains **absent**: `readiness FAIL → alert → [MISSING] → dispatch
proceeds`. #615 detects and vetoes nothing. If recovery does not complete before 2026-08-10
10:24 ET, the ruling must be revisited and the fallback is a narrowly governed temporary
disablement of only strategies 7 and 8, recorded on both disablement and restoration.

## 7. Failure disposition

```
PRODUCTION_REFRESH_RECOVERY_FAILED
  timer disabled · previous sealed store retained · dispatch interlock closed
  evidence preserved · live store left untouched
```

## 8. Owner approval

Approved for the limited purpose of restoring the production factor-refresh producer on the paper
box. No broker order authority is granted.

```
approved_by  Jay Wang (GlobalComplyAI LLC), owner
issued_at    2026-08-05T00:00:00Z
```
