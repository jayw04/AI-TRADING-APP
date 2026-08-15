# MDQ-001 — Algo Trader Plus / SIP Market-Data Qualification — Registration

| Field | Value |
|---|---|
| Program | **MDQ-001** |
| Version | v1.0 **DRAFT — not yet registered** |
| Date | 2026-08-15 |
| Class | Platform data-qualification track (Research/Analytics plane, ADR 0051). **Not alpha research.** No execution authority; outputs are governed artifacts carrying the standard provenance envelope. |
| Governing plan | `docs/Strategies/Strategy-proposals-v1_4_1-Algo-Trader-Plus-2026-08-15.md` §1.3, §4, §15 Track A |
| Decision owner | **Platform owner (Jay Wang)** |
| Entitlement date | **2026-08-15** — Algo Trader Plus, **switched same day to the workbench-account-7 login** (`ALPACA_PAPER_6` credential, broker `PA3BGKRLH2AP`); no other credential is entitled as of the late-day 2026-08-15 probe (§7) |
| Calendar review trigger | **Entitlement date + 60 days = 2026-10-14** (restarts from the MDQ entitlement date if §7 option 1 or 3 is chosen) |
| Registration semantics | The K1–K6 / C1 values below are **frozen at registration, before data collection**. The owner may adjust them **only at registration sign-off (§8), never afterward**. |

---

## 1. Goal

Determine whether SIP (and, for the bounded OPRA capture, options) data materially improves Trading Workbench market observation, scanner coverage, intraday evidence, and execution diagnostics enough to justify permanent use and the $99/month subscription — judged **net of cost** (subscription + incremental storage/compute attributable to MDQ-001/OPRA-CAP-001).

MDQ-001 produces **no** strategy signal, changes **no** strategy behavior, and reopens **no** settled strategy decision.

## 2. Registration preconditions

- **P-1 (done):** feed pinning landed before qualification work — the §15 A1 gaps are closed and `check_marketdata_feed_pinning.sh` passes (2026-08-15). No governed path can silently change feed semantics under the entitlement.
- **P-2 (open):** confirm the **real-time** (vs delayed) tier of the entitled credential during RTH (Monday 2026-08-17, or the Alpaca dashboard). As of the 2026-08-15 late-day probes, exactly **one** credential passes the discriminating SIP latest-quote check: **`ALPACA_PAPER_6`** — the login of **workbench account 7** (broker `PA3BGKRLH2AP`). The unnumbered and `_7` credentials, which passed earlier the same day, now 403: the subscription was **switched**, not added. **Registration should not be signed before P-2 resolves**, since K2/K6 assume real-time SIP.
- **P-3 (resolved by owner ruling, 2026-08-15):** credential/subscription assignment — Option 2A adopted, see §7. No second subscription; account 7 is the sole SIP acquisition identity; MDQ-001 is an offline/read-only consumer and receives no Alpaca credentials.

## 3. Scope — qualification tests (frozen from plan §4.2)

| Test | Substance |
|---|---|
| **A. IEX-vs-SIP census** | Latest trade/quote, 1-min OHLCV, trade count, VWAP, spread, premarket/RTH volume, missing bars, bar timestamps; derived features (gap, RVOL, ATR, VWAP, opening range, scanner eligibility, candidate rank). ΔVolume recorded as a **diagnostic only** (not a keep trigger, v1.4.1 K1 correction). |
| **B. Streaming reliability** | Uptime, reconnects, dropped/late/duplicate/out-of-order messages, per-symbol lag, open-burst behavior, resource use, restart recovery. |
| **C. Broad-universe scalability** | 50 → 250 → 500 symbols; scale justified by scanner/research need, never by entitlement. |
| **D. Historical throughput** | Build a reproducible SIP research extract: date-bounded, feed-explicit, identity-bound, immutable after freeze, separated from the live cache. *Under §7, the immutable capture store IS this extract — Test D and the acquisition architecture are the same artifact.* |
| **E. OPRA intake (`OPRA-CAP-001`)** | Bounded capture per plan §15 A6: pre-declared underlyings (SPY/QQQ/IWM + sector ETFs), snapshot cadence (15-min IV surface), pre-declared storage budget. No tick archive; no options trading. |

## 4. Keep / cancel criteria — FROZEN AT REGISTRATION

Proposed values below are the plan's §4.3 defaults verbatim; the owner may adjust only in §8.

**Keep the subscription if ANY K criterion is met:**

- **K1 — scanner/decision materiality:** SIP changes SCAN-001 eligibility, ranking, or GAPPER-relevant upstream classification on ≥ **10%** of evaluated session-days, **or** corrects ≥ 1 predeclared gate-material IEX observation defect that would otherwise alter eligibility or risk disposition. ΔVolume is a required diagnostic, **not** a keep trigger.
- **K2 — streaming reliability:** ≥ **99.5%** session uptime over **20 consecutive sessions** at ≥ **250** symbols, zero unrecovered data gaps. *Under the §7 architecture, K2 is measured on the **collector** (Phase B), which is the only process that streams — and Phase B requires its own separately opened authorization (plan v0.3 gate **G10**: non-contention proof vs account 7, WebSocket feed identity, one-connection/dual-arming analysis, ceiling + abort rule, own session doc). Phase A is REST-only, so unless G10 opens within the MDQ window, K2 is scored **NOT EVALUABLE** — which is not FAIL, and which cannot itself satisfy GO (only a met K criterion can). Same treatment as K4.*
- **K3 — data completeness:** missing-bar rate reduced ≥ **50%** vs IEX on the qualification universe. *Frozen metric definition (2026-08-15, tightened per plan v0.3 §4.2): the comparison grid `U` is the **union** of `(symbol, session_date, minute_ts)` keys observed by either feed within the Phase-A bar window (04:00–16:00 ET) — minutes where **neither** feed reports a bar are outside `U`. Per feed: `missing_rate_f = 1 − observed_keys_f / |U|`. K3 is met when `(missing_rate_IEX − missing_rate_SIP) / missing_rate_IEX ≥ 0.50`. If `missing_rate_IEX = 0`, K3 is **not evaluable on that grid** — no division, no artificial pass. Raw row-count ratios are **diagnostic only**, and the pre-registration smoke may not be used to choose or tune this definition.*
- **K4 — GAPPER Stage-0 enablement:** SIP supplies required upstream fields the incumbent feed measurably cannot (per the Stage-0 field-sufficiency report). *Note: evaluable only to the extent GAPPER v2.1.1 Stage 0 runs inside the window; its start awaits the owner's §9 sequencing ruling. If Stage 0 has not run by the review date, K4 is scored "not evaluable", not "failed".*
- **K5 — execution evidence:** spread/mid/shortfall metrics produced for ≥ **90%** of paper fills in the period. *Frozen population/matching policy (per plan v0.3 §4.3, values fixed at §8 sign-off): which paper accounts/programs form the denominator; whether only Phase-A-universe symbols count; the submission/fill timestamp source of record; the quote-match rule (at-or-before vs nearest); the maximum quote age/tolerance; and the treatment of fills with no valid quote. No matching tolerance may be chosen after seeing coverage.*
- **K6 — quote fidelity:** **zero** recurrence in SIP data of the IEX stub-quote artifact class (single-venue quote implying a spread ≥ **100 bps** wider than consolidated NBBO — cf. 2026-08-14 GLD incident), measured over the qualification period against ≥ 1 observed IEX occurrence.

**Cancel (C1):** no K criterion met, judged **net of cost** — measured value vs subscription **plus** incremental storage/compute attributable to MDQ-001/OPRA-CAP-001.

**Pre-registration quarantine:** thresholds freeze **before** data collection, so any capture made before §8 sign-off carries the manifest label `PRE_REGISTRATION_SMOKE` and is **inadmissible** to K1–K6/C1 — engineering/implementation evidence only. The 2026-08-14 collector smoke (IEX 4,818 vs SIP 7,057 one-minute bar rows on the 14-symbol default universe, ≈46% more SIP rows) is exactly such evidence: an encouraging coverage indication, but it measures extra bars, not the K3 missing-bar-rate metric, and it never enters the qualification corpus.

**Admissible corpus (frozen, per plan v0.3 §7):** a partition enters the K1–K6 corpus only if ALL hold — captured after §8 sign-off; credential/account identity latch passed; explicit feed identity present; universe/cadence/session scope match the frozen identity; freeze completed and `verify` passes; the manifest lists all expected files with no unmanifested strays; the collector code identity is approved for the period; no post-freeze mutation. Excluded categorically: the pre-registration smoke, scratchpad/manual exploratory captures, unpinned-credential captures, scope-mismatched partitions, unfrozen partitions, failed hash verification, and any recovered/reconstructed file whose bytes are not the originally frozen bytes.

## 5. Verdict format

One recorded disposition at the review date, as a governed artifact (ADR 0051 envelope), mirroring the GAPPER v2 pattern:

- **GO** — retain subscription; open the governed SIP adoption path (plan §3.3 migration rule per strategy/program).
- **HOLD** — extend **exactly one** additional period, for a named reason stated at the verdict.
- **STOP** — cancel; unwind pinned-SIP paths back to `feed=iex`.

## 6. Operational constraints (frozen from plan §4.5, restated for the §7 architecture)

1. **Execution environment and storage:** the collector and the raw-data store live on the **governed AWS host's local persistent volume**; MDQ analysis runs on the AWS box, WSL, or CI — **never the laptop** (warm-standby host; must not arm Alpaca data websockets; TLS-interception history disqualifies it for reliability measurement). S3 archival of frozen partitions may be added later under the standard manifest discipline; local disk is the system of record first.
2. **Single acquisition identity, no dual-arming:** the collector (authenticating as `_6`, resolved by **fingerprint, never env-var name**) is the only new process allowed to arm an Alpaca data websocket. MDQ-001 arms nothing (§7 control 1). The live paper stack's existing IEX stream (unnumbered credential) is untouched until the platform-wide consumer migration (§7, "beyond MDQ") lands under its own ADR.
3. **Licensing boundary (recorded 2026-08-15, owner):** the subscription is not blanket permission for commercial reuse. Alpaca's Customer Agreement forbids reproducing, distributing, selling, or commercially exploiting market data without written consent; private internal strategy research is the intended use case and proceeds. Before Trading Workbench exposes stored SIP data to other users, redistributes it, or becomes a commercial service over it, obtain Alpaca's written clarification. This is a recorded boundary, not a blocker for internal Phase-A qualification.
4. **Durability policy (per plan v0.3 §4.7 — decided at §8 sign-off):** manifests + SHA-256 prove *integrity*, not *survival* of the box's local volume (which has been destroyed once before, 2026-07-27). Before the 60-day corpus becomes authoritative, either (a) frozen partitions are mirrored **byte-for-byte** to a governed off-host store (recommended: the existing S3 governed-artifact pattern, Version-ID pinned) after local `verify` passes — mirroring must never rewrite data or provenance — or (b) the owner explicitly accepts local-volume loss risk for this qualification cycle.
5. **Collector ceiling:** the collector and any MDQ batch job on the shared live host carry a pre-declared CPU/memory/storage ceiling and an abort rule that fires before the execution backend degrades. Measurable degradation is ADR 0051's first Phase-2 trigger — record it as trigger evidence; do not push through. *Proposed ceiling (owner may adjust at sign-off): ≤ 50% of one vCPU, ≤ 1 GB RSS, ≤ 20 GB persistent store budget for capture partitions (alert at 15 GB), ≤ 5 GB scratch for analysis; abort on 2 consecutive minutes above ceiling or any live-stack health-check failure. The collector is always subordinate to the account-7 transition executor (§7 control 5).*

## 7. Credential / subscription assignment — OWNER DECISION REQUIRED

Probe history, 2026-08-15 (SIP latest-quote, the discriminating endpoint):

| Credential | Midday | Late day (post-switch) | Identity |
|---|---|---|---|
| unnumbered | 200 | **403** | live stack's data-websocket identity |
| `ALPACA_PAPER_7` | 200 | **403** | ADR-0043 WSS canary; no workbench account |
| `ALPACA_PAPER_6` | 403 | **200 — only entitled cred** | **workbench acct 7**, broker `PA3BGKRLH2AP` |

The single Plus subscription now rides the **account-7 login** — consistent with the owner ruling in the acct-7 transition program (P0-A: entitle acct-7's own login so its executor can move to SIP). That subscription's *purpose* is acct-7's spread-gate fix, and its login is a heavily governed live account.

### Adopted: Option 2A — shared acquisition, isolated offline qualification *(owner ruling, 2026-08-15)*

> **Ruling:** No second subscription. Account 7 is the sole SIP acquisition identity. MDQ-001 is an offline/read-only consumer of immutable SIP captures. Direct MDQ-001 authentication to Alpaca using `_6` is prohibited. High-load streaming/scalability qualification is deferred until it can be performed without impairing account-7 execution.

Data flow — **capture once, analyze many times**:

```text
Alpaca SIP ──> account-7 collector ──> immutable raw-data store ──> MDQ-001
              (only process that        (governed AWS host,          (offline, read-only;
               authenticates; _6)        local persistent volume)     no Alpaca calls ever)
```

**Five required controls:**

1. **Account 7 owns acquisition.** The collector is the only process permitted to authenticate with `_6` for SIP capture. MDQ-001 receives **no** Alpaca credentials and makes **no** API or websocket calls — the feed-pinning guard's no-implicit-feed rule is thereby vacuous for MDQ analysis code, which touches only files.
2. **Raw data first.** The collector persists raw quote/trade/bar records into time-partitioned files (`sip/YYYY-MM-DD/{quotes,trades,bars}/…`). MDQ-001 never queries the live cache. To make IEX-vs-SIP comparisons time-aligned, the collector also captures the paired IEX observations under the same partition scheme (`iex/YYYY-MM-DD/…`) — both feeds explicit, per the §3.1 rule.
3. **Provenance with every capture.** Each partition carries a manifest: `feed` literal, account/credential **fingerprint** (never the secret), collector version/hash, symbol universe, start/end timestamps, capture mode, Alpaca endpoint/schema version where available, and per-file SHA-256. This is the ADR 0051 envelope's market-data input manifest, not a parallel scheme.
4. **Freeze completed partitions.** The collector writes today's partition; MDQ-001 reads only **frozen** (completed-session) partitions, read-only. Research activity can never interfere with live acquisition.
5. **Collector ceiling, subordinate to the executor.** The collector carries an explicit resource/rate ceiling (§6.5) and its workload is **subordinate to the account-7 transition executor** — acquisition still spends account 7's data allowance, so contention is bounded at the collector, the single place it can occur.

Per ADR 0051 decision 6, the immutable capture store's **single designated writer is the collector**; MDQ-001 and all other consumers are readers.

**Phasing (K2 exception):** K2 cannot be honestly measured from data account 7 happens to collect for its executor — it requires the collector itself to hold the ≥250-symbol universe for 20 sessions.

- **Phase A — passive/offline (starts on registration):** capture = whatever account 7's transition already needs **plus a modest predeclared capture universe** (frozen at sign-off, §8). Capture is **REST-only** (paired latest-quote sampling + end-of-session 1-minute bars over **04:00–16:00 ET** — premarket + RTH, the registered census scope; postmarket is not collected without a qualification reason). REST-only is also the safe posture against Alpaca's documented one-WebSocket-connection-per-endpoint limit on most subscriptions including Plus. K1/K3/K4/K5/K6 run entirely offline against frozen partitions.
- **Phase B — K2 scalability qualification (gated):** the controlled ≥250-symbol streaming capture for 20 consecutive sessions, started only once account-7's transition workload is stable and the collector can run without impairing it. Still writes locally; MDQ-001 still never connects to Alpaca.

**Rejected alternatives** (recorded so they are not re-litigated): a second $99/mo subscription on a dedicated credential (unnecessary given the boundary above); direct MDQ use of `_6` under scheduling (weaker separation — the boundary beats the calendar); full deferral of MDQ-001 (only the K2/scale portion needs to wait).

### Beyond MDQ — the acquisition boundary as platform architecture *(owner ruling, 2026-08-15)*

The owner's ruling extends past MDQ-001: **account 7 is the platform's single market-data acquisition identity, the AWS box's local store is the system of record, and all apps become local-store consumers.** MDQ-001 is simply the *first* offline consumer and proves the store's fitness.

Scope boundary this document deliberately does not cross: migrating the **live stack's existing consumers** (bar cache, quote service, risk-gate price reads, strategy bars — today direct Alpaca IEX calls on the unnumbered credential) onto the local store changes the **order path's data dependency** and the platform's failure modes (collector down ⇒ stale prices for gates). That migration requires its own **ADR** (staged cutover, freshness/staleness contract per consumer, fallback policy, feed-identity preservation through the store), plus per-strategy treatment under the plan's §3.3 migration rule where feed values change. Until that ADR lands, live consumers stay exactly as they are; nothing in MDQ-001 touches them.

## 8. Registration sign-off (owner)

Signing freezes §4 values (including the K3 metric and K5 population/matching policy), the §6.5 ceiling, the §6.4 durability choice, the sampler cadence/retry policy, and the §7 assignment. After signature, thresholds are immutable for the life of MDQ-001; the only later dispositions are the §5 verdicts.

```
K1–K6 / C1 values:        [ ] accepted as proposed   [ ] adjusted at registration to: ____________
Collector ceiling (§6.5): [ ] accepted as proposed   [ ] adjusted to: ____________
K5 population/matching:   [ ] denominator = all paper fills, Phase-A symbols only;
                              quote match = at-or-before, max age 5s; no-quote fills
                              excluded from numerator AND denominator (proposed)
                          [ ] adjusted to: ____________
Durability (§6.4):        [ ] S3 byte-for-byte mirror after verify (Recommended)
                          [ ] accept local-volume loss risk this cycle
Sampler cadence/retry:    [ ] 60s cadence; per-feed error capture; continue on
                              transient failure; abort after 30 consecutive
                              failed cycles (proposed)   [ ] adjusted to: ____
Architecture (§7):        [X] Option 2A adopted by owner ruling 2026-08-15 — account-7 collector,
                              immutable local store on the AWS box, MDQ offline/read-only,
                              no MDQ Alpaca credentials; K2 deferred to Phase B.
Phase-A capture universe: [ ] as proposed (SPY/QQQ/IWM + sector ETFs + acct-7 transition set
                              + predeclared scanner sample ≤ 50 symbols)   [ ] adjusted to: ____
P-2 real-time tier:       [ ] verified 2026-08-17 RTH   [ ] verified via dashboard
Registered by / date:     ______________________
```

## 9. Authority

Planning/qualification governance only. If this document conflicts with a frozen pre-registration, sealed verdict, owner ruling, hash-bound design, ADR, or promotion gate, the governed program artifact controls. MR-002 HOLD and the GAPPER v2.1.1 §9 sequencing are unaffected by anything here.
