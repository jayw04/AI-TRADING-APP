# MDQ-001 — Algo Trader Plus / SIP Market-Data Qualification — Registration

| Field | Value |
|---|---|
| Program | **MDQ-001** |
| Version | v1.0 **DRAFT — not yet registered** (updated 2026-08-15 per implementation-plan v0.5; **correction set applied 2026-08-18** — owner rulings 1–4, recorded in **§8.2**. Three are consistency corrections to prose a later ratified decision had already superseded; the fourth **adds a disposition** (§5) and was **SIGNED 2026-08-19 at §8.3**, before any exploratory read of the corpus. The signed §8 block and the ratified §8.1 block are not edited.) |
| Date | 2026-08-15 |
| Class | Platform data-qualification track (Research/Analytics plane, ADR 0051). **Not alpha research.** No execution authority; outputs are governed artifacts carrying the standard provenance envelope. |
| Governing plan | `docs/Strategies/Strategy-proposals-v1_4_1-Algo-Trader-Plus-2026-08-15.md` §1.3, §4, §15 Track A |
| Decision owner | **Platform owner (Jay Wang)** |
| Entitlement date | **2026-08-15** — Algo Trader Plus, **switched same day to the workbench-account-7 login** (`ALPACA_PAPER_6` credential, broker `PA3BGKRLH2AP`); no other credential is entitled as of the late-day 2026-08-15 probe (§7) |
| Calendar review trigger | **First admissible governed capture + 60 days** *(re-anchored per plan v0.5 §2 G3)* — the clock runs from the first admissible governed capture, **not** the entitlement date; the resulting review date is computed and frozen at §8 sign-off (target ~2026-10-14 assuming no pre-deployment slip). A deployment slip moves the review date; it never silently shortens the evidence window. |
| Registration semantics | The K1–K6 / C1 values below are **frozen at registration, before data collection**. The owner may adjust them **only at registration sign-off (§8), never afterward**. |

---

## 1. Goal

Determine whether SIP (and, for the bounded OPRA capture, options) data materially improves Trading Workbench market observation, scanner coverage, intraday evidence, and execution diagnostics enough to justify permanent use and the $99/month subscription — judged **net of cost** (subscription + incremental storage/compute attributable to MDQ-001/OPRA-CAP-001).

MDQ-001 produces **no** strategy signal, changes **no** strategy behavior, and reopens **no** settled strategy decision.

## 2. Registration preconditions

- **P-1 (done):** feed pinning landed before qualification work — the §15 A1 gaps are closed and `check_marketdata_feed_pinning.sh` passes (2026-08-15). No governed path can silently change feed semantics under the entitlement.
- **P-2 (open):** confirm the **real-time** (vs delayed) tier of the entitled credential during RTH (Monday 2026-08-17, or the Alpaca dashboard). As of the 2026-08-15 late-day probes, exactly **one** credential passes the discriminating SIP latest-quote check: **`ALPACA_PAPER_6`** — the login of **workbench account 7** (broker `PA3BGKRLH2AP`). The unnumbered and `_7` credentials, which passed earlier the same day, now 403: the subscription was **switched**, not added. **Registration should not be signed before P-2 resolves**, since K2/K6 assume real-time SIP.
- **P-3 (resolved by owner ruling, 2026-08-15):** credential/subscription assignment — Option 2A adopted, see §7. No second subscription; account 7 is the sole SIP acquisition identity; the **Phase-A collector is the sole authenticating component**; MDQ-001 analysis/calculators are offline read-only consumers and receive no Alpaca credentials.
- **P-4 (open, added per plan v0.5):** the feed-pinning guard `check_marketdata_feed_pinning.sh` is enforced in CI (the separate CI-wiring PR, per the owner's prior ruling) **before the first governed capture**. An unwired guard is convention, not mechanism. This is a precondition of collector **deployment** (G2), not of the code-review merge.

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

**GO — retain the subscription only if at least two of K1–K6 are both EVALUABLE and PASS.** A NOT EVALUABLE criterion neither passes nor fails and cannot contribute toward the GO floor.

> *Edit note — 2026-08-18, owner ruling 2 (**CORRECTION** to stale prose; **not** a reopening).* This line previously read “Keep the subscription if **ANY** K criterion is met.” That wording predates — and contradicts — the later, specifically ratified §8.1 GO floor (“GO requires at least two of K1–K6 to be BOTH evaluable AND PASS”). **§8.1 controls**; the §4 sentence was simply never updated when §8.1 was ratified. The ratified threshold is unchanged and is not reopened here, and neither the signed §8 block nor the ratified §8.1 block is edited. See §8.2 ruling 2.

- **K1 — scanner/decision materiality:** SIP changes SCAN-001 eligibility, ranking, or GAPPER-relevant upstream classification on ≥ **10%** of evaluated session-days, **or** corrects ≥ 1 predeclared gate-material IEX observation defect that would otherwise alter eligibility or risk disposition. ΔVolume is a required diagnostic, **not** a keep trigger.
- **K2 — streaming reliability:** ≥ **99.5%** session uptime over **20 consecutive sessions** at ≥ **250** symbols, zero unrecovered data gaps. *Under the §7 architecture, K2 is measured on the **collector** (Phase B), which is the only process that streams — and Phase B requires its own separately opened authorization (plan v0.3 gate **G10**: non-contention proof vs account 7, WebSocket feed identity, one-connection/dual-arming analysis, ceiling + abort rule, own session doc). Phase A is REST-only, so unless G10 opens within the MDQ window, K2 is scored **NOT EVALUABLE** — which is not FAIL, and which cannot itself satisfy GO (only a met K criterion can). Same treatment as K4.*
- **K3 — data completeness:** missing-bar rate reduced ≥ **50%** vs IEX on the qualification universe. *Frozen metric definition (2026-08-15, tightened per plan v0.3 §4.2): the comparison grid `U` is the **union** of `(symbol, session_date, minute_ts)` keys observed by either feed within the Phase-A bar window (04:00–16:00 ET) — minutes where **neither** feed reports a bar are outside `U`. Per feed: `missing_rate_f = 1 − observed_keys_f / |U|`. K3 is met when `(missing_rate_IEX − missing_rate_SIP) / missing_rate_IEX ≥ 0.50`. If `missing_rate_IEX = 0`, K3 is **not evaluable on that grid** — no division, no artificial pass. Raw row-count ratios are **diagnostic only**, and the pre-registration smoke may not be used to choose or tune this definition.*
- **K4 — GAPPER Stage-0 enablement:** SIP supplies required upstream fields the incumbent feed measurably cannot (per the Stage-0 field-sufficiency report). *Note: evaluable only to the extent GAPPER v2.1.1 Stage 0 runs inside the window; its start awaits the owner's §9 sequencing ruling. If Stage 0 has not run by the review date, K4 is scored "not evaluable", not "failed" — and it drops out of the keep/cancel denominator: a scheduling artifact unrelated to SIP must not count toward C1 (plan v0.5 §8.8).*
- **K5 — execution evidence:** spread/mid/shortfall metrics produced for ≥ **90%** of paper fills in the period. *Frozen population/matching policy (per plan v0.3 §4.3, values fixed at §8 sign-off): which paper accounts/programs form the denominator; whether only Phase-A-universe symbols count; the submission/fill timestamp source of record; the quote-match rule (at-or-before vs nearest); the maximum quote age/tolerance; and the treatment of fills with no valid quote. No matching tolerance may be chosen after seeing coverage. **Minimum-population floor (plan v0.5 §4.3):** §8 freezes a minimum admissible fill count `N_min` (proposed **50** fills across the qualifying programs within the review window). With MR-002 on HOLD and GAPPER Stage 0 not executing, the denominator may be very small, and "≥90% of a handful of fills" measures nothing. Below `N_min`, K5 is **NOT EVALUABLE** — not FAIL, and it cannot itself satisfy GO. The floor is frozen before evidence accrues and never adjusted after seeing the count.*
- **K6 — quote fidelity:** **zero** recurrence in SIP data of the IEX stub-quote artifact class (single-venue quote implying a spread ≥ **100 bps** wider than consolidated NBBO — cf. 2026-08-14 GLD incident), measured over the qualification period against ≥ 1 observed IEX occurrence. *Evaluability (plan v0.5 §4.8): Phase A samples latest quotes at a 60-second cadence; a transient stub quote can appear and clear entirely between samples, so the required IEX-side occurrence is not guaranteed observable from Phase-A capture alone. §8 chooses exactly one resolution, before evidence accrues: **(a) recommended** — K6 is **NOT EVALUABLE unless ≥ 1 IEX stub-quote occurrence is captured in the admissible corpus** (NOT EVALUABLE is not FAIL and cannot itself satisfy GO — the K2 language); or **(b)** the live executor's spread-gate rejection log — where the 2026-08-14 GLD incident was actually detected — is admitted as the IEX-side occurrence source, with the SIP-side comparison drawn from the Phase-A capture at the matching `cycle_ts`; option (b) requires the rejection-log schema, the match tolerance, and that log's admissibility as governed evidence to be frozen at §8. The sampling cadence is frozen identity (§8) and may not be tightened after seeing results.*

**Cancel (C1):** no K criterion met, judged **net of cost** — measured value vs subscription **plus** incremental storage/compute attributable to MDQ-001/OPRA-CAP-001. *Criteria scored NOT EVALUABLE (K2 without G10; K4 without an in-window Stage-0 run; K5 below `N_min`; K6 without an observed occurrence under its option (a)) leave the keep/cancel denominator entirely: they can neither satisfy GO nor count toward Cancel (plan v0.5 §8.8).*

> *Edit note — 2026-08-18, owner ruling 3 (scope clarification here; the **addition** itself lives in §5).* Read with the §8.1 GO floor, C1/STOP is the case **≥ 2 criteria evaluable and 0 PASS**. The bare wording “no K criterion met” is what left the **≥ 2 evaluable and exactly 1 PASS** case with no disposition at all — not GO, not STOP, and not covered by §8.1’s HOLD clause, which addresses *fewer than two evaluable*. The completed disposition table is in **§5**; its fourth row was an addition requiring explicit owner sign-off and was **signed 2026-08-19 at §8.3** — not by this note. The C1 threshold itself is unchanged.

**Pre-registration quarantine:** thresholds freeze **before** data collection, so any capture made before §8 sign-off carries the manifest label `PRE_REGISTRATION_SMOKE` and is **inadmissible** to K1–K6/C1 — engineering/implementation evidence only. The 2026-08-14 collector smoke (IEX 4,818 vs SIP 7,057 one-minute bar rows on the 14-symbol default universe, ≈46% more SIP rows) is exactly such evidence: an encouraging coverage indication, but it measures extra bars, not the K3 missing-bar-rate metric, and it never enters the qualification corpus.

**Admissible corpus (frozen, per plan v0.5 §7):** a partition enters the K1–K6 corpus only if ALL hold — captured after §8 sign-off; credential/account identity latch passed; explicit feed identity present; universe/cadence/session scope match the frozen identity; freeze completed and `verify` passes; the manifest lists all expected files with no unmanifested strays; the collector code identity is approved for the period; no post-freeze mutation; **and the partition meets the frozen completeness thresholds** (plan v0.5 §4.9). Completeness is not integrity: `verify` proves the bytes are the frozen bytes, not that the partition contains the observations it was supposed to contain — at 60-second cadence, the abort-after-30-consecutive-failed-cycles rule permits a ~30-minute hole that still freezes and still passes `verify` (the GAPPER v1 failure mode: records present, sufficiency absent). Define `expected_cycles = f(session_scope, cadence, market calendar)`, `observed_cycles` = admissible non-error observations, `completeness = observed_cycles / expected_cycles`; §8 freezes a **minimum completeness** (proposed **≥ 98%** per partition per feed) and a **maximum contiguous gap** (proposed **10 minutes**) independent of the aggregate rate. `feed_error` records count toward the denominator, never the numerator. Excluded categorically: the pre-registration smoke, scratchpad/manual exploratory captures, unpinned-credential captures, scope-mismatched partitions, unfrozen partitions, failed hash verification, any recovered/reconstructed file whose bytes are not the originally frozen bytes, and partitions failing the completeness thresholds **even where `verify` passes**.

> *Edit note — 2026-08-18, owner ruling 1 (**CORRECTION**: binds a definition this document left unbound; **no threshold changes**).* §8 froze the completeness **threshold** but left `session_scope` inside `expected_cycles = f(session_scope, cadence, market calendar)` unbound, and the only session interval this document names is **04:00–16:00 ET** — which is the **EOD one-minute bar census scope**, *not* the quote-sampler denominator. Using the census interval as the sampler denominator would mechanically fail every healthy partition, and nothing would ever be admissible. The frozen sampler denominator is:

```text
sampler_start   = 09:25 America/New_York
sampler_end     = official NYSE close for that session, EXCLUSIVE
cadence         = 60 seconds
expected_cycles = count of scheduled cadence slots t such that
                  sampler_start <= t < sampler_end
```

> ⇒ **395** cycles on a normal 16:00 close · **215** on a 13:00 early close · **0** on holidays and other non-session days. The **market calendar controls** early closes and non-trading days. The **98% minimum completeness and the 10-minute maximum contiguous gap are UNCHANGED** — the fix is the definition, not the threshold. The bar-census scope stays 04:00–16:00 ET and remains the denominator on the bar side. Full text, including the related scheduler-drift ruling, at **§8.2 ruling 1**.

## 5. Verdict format

One recorded disposition at the review date, as a governed artifact (ADR 0051 envelope), mirroring the GAPPER v2 pattern:

- **GO** — retain subscription; open the governed SIP adoption path (plan §3.3 migration rule per strategy/program).
- **HOLD** — extend **exactly one** additional period, for a named reason stated at the verdict.
  *(§8.3 adds two invocation requirements to this rule without changing it: the verdict must also state the **extension duration** and the **next adjudication date**, and a repeat of the triggering cell at that next adjudication resolves to **STOP**.)*
- **STOP** — cancel; unwind pinned-SIP paths back to `feed=iex`.

**Disposition table — which review result produces which verdict** *(added 2026-08-18, owner ruling 3)*

| Review result | Disposition |
|---|---|
| ≥ 2 criteria evaluable and ≥ 2 PASS | **GO** |
| ≥ 2 criteria evaluable and 0 PASS | **STOP** |
| Fewer than 2 criteria evaluable | **HOLD**, one stated extension |
| ≥ 2 criteria evaluable and **exactly 1 PASS** | **HOLD**, exactly one additional period — **SIGNED, §8.3** |

> ✅ **The fourth row is SIGNED (§8.3, 2026-08-19).**
>
> Rows 1–3 restate decisions that were already ratified: rows 1 and 3 are the §8.1 GO floor verbatim, and row 2 is C1 read with that floor. **Row 4 was different in kind** — the combined rules genuinely left `≥ 2 evaluable and exactly 1 PASS` **undefined**: not GO (which needs ≥ 2 passes), not STOP under the old “no K criterion met” wording (one criterion *was* met), and not covered by §8.1’s HOLD clause (which addresses *fewer than two evaluable*). Assigning it HOLD therefore **added a disposition rather than correcting stale prose**, which is why it required an explicit signature rather than being ratified by its presence in this table.
>
> It was signed on **2026-08-19**, **before any exploratory read of the corpus** and therefore before §8.1’s evidence firewall closed the ability to revise a verdict or evaluability clause. The full signed ruling, including the two invocation requirements it adds to every HOLD, is at **§8.3**; the §8.2 ruling-3 stanza is completed accordingly.

## 6. Operational constraints (frozen from plan §4.5, restated for the §7 architecture)

1. **Execution environment and storage:** the collector and the raw-data store live on the **governed AWS host's local persistent volume**; MDQ analysis runs on the AWS box, WSL, or CI — **never the laptop** (warm-standby host; must not arm Alpaca data websockets; TLS-interception history disqualifies it for reliability measurement). S3 archival of frozen partitions may be added later under the standard manifest discipline; local disk is the system of record first.
2. **Single acquisition identity, no dual-arming:** the collector (authenticating as `_6`, resolved by **fingerprint, never env-var name**) is the only new process allowed to arm an Alpaca data websocket. MDQ-001 arms nothing (§7 control 1). The live paper stack's existing IEX stream (unnumbered credential) is untouched until the platform-wide consumer migration (§7, "beyond MDQ") lands under its own ADR.
3. **Licensing boundary (recorded 2026-08-15, owner):** the subscription is not blanket permission for commercial reuse. Alpaca's Customer Agreement forbids reproducing, distributing, selling, or commercially exploiting market data without written consent; private internal strategy research is the intended use case and proceeds. Before Trading Workbench exposes stored SIP data to other users, redistributes it, or becomes a commercial service over it, obtain Alpaca's written clarification. This is a recorded boundary, not a blocker for internal Phase-A qualification.
4. **Durability policy (per plan v0.3 §4.7 — decided at §8 sign-off):** manifests + SHA-256 prove *integrity*, not *survival* of the box's local volume (which has been destroyed once before, 2026-07-27). Before the 60-day corpus becomes authoritative, either (a) frozen partitions are mirrored **byte-for-byte** to a governed off-host store (recommended: the existing S3 governed-artifact pattern, Version-ID pinned) after local `verify` passes — mirroring must never rewrite data or provenance — or (b) the owner explicitly accepts local-volume loss risk for this qualification cycle.
5. **Collector ceiling:** the collector and any MDQ batch job on the shared live host carry a pre-declared CPU/memory/storage ceiling and an abort rule that fires before the execution backend degrades. Measurable degradation is ADR 0051's first Phase-2 trigger — record it as trigger evidence; do not push through. *Proposed ceiling (owner may adjust at sign-off): ≤ 50% of one vCPU, ≤ 1 GB RSS, ≤ 20 GB persistent store budget for capture partitions (alert at 15 GB), ≤ 5 GB scratch for analysis; abort on 2 consecutive minutes above ceiling or any live-stack health-check failure. The collector is always subordinate to the account-7 transition executor (§7 control 5).*
   *Shared-host disk protection (plan v0.5 §4.9): `WORKBENCH_MDQ_CAPTURE_ROOT` shares the AWS persistent volume with the live execution backend and the SQLite trading book, so the ceiling gains an explicit disk floor. §8 freezes a **free-space floor** (proposed: the greater of **10 GB** or **20%** of the volume) checked **before each write cycle and before EOD/freeze**; on breach the collector **aborts and alerts** — it never writes into the floor. A per-partition size ceiling consistent with the OPRA-CAP-001 storage budget applies, and freeze failures alert via the daily-report watchdog rather than failing silently. Capture-induced degradation of the execution backend is ADR 0051's first Phase-2 trigger — record it as trigger evidence; never engineer around it in place.*

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
3. **Provenance with every capture.** Each partition carries a manifest: `feed` literal, account/credential **fingerprint** (never the secret), collector version/hash, symbol universe, start/end timestamps, capture mode, Alpaca endpoint/schema version where available, and per-file SHA-256. This is the ADR 0051 envelope's market-data input manifest, not a parallel scheme. *Identity-latch payload discipline (plan v0.5 §3.1): the pinned read-only `GET /v2/account` call returns execution-plane state (equity, buying power) alongside the broker id; the latch asserts the fingerprint/broker identity and **discards the remainder** — no account balances are ever logged or persisted into the research archive. Because Phase A runs in-process on the shared host, ADR 0051's first state applies (research code holds no execution authority, enforced by the structural pytest invariant); the pinned identity call is conformant, not an exception.*
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

Signing freezes §4 values (including the K3 metric, the K5 population/matching policy and `N_min` floor, the K6 evaluability choice, and the partition-completeness thresholds), the §6.5 ceiling and free-space floor, the §6.4 durability choice, the sampler cadence/retry policy, the review-date anchor, and the §7 assignment. After signature, thresholds are immutable for the life of MDQ-001; the only later dispositions are the §5 verdicts.

```
K1–K6 / C1 values:        [X] accepted as proposed   [ ] adjusted at registration to: ____________
Collector ceiling (§6.5): [X] accepted as proposed   [ ] adjusted to: ____________
K5 population/matching:   [X] denominator = all paper fills, Phase-A symbols only;
                              quote match = at-or-before, max age 5s; no-quote fills
                              excluded from numerator AND denominator (proposed)
                          [ ] adjusted to: ____________
K5 minimum fills N_min:   [X] 50 (proposed; below it K5 = NOT EVALUABLE)
                          [ ] adjusted to: ____________
K6 evaluability:          [X] (a) NOT EVALUABLE unless >= 1 IEX stub-quote occurrence
                              in the admissible corpus (Recommended)
                          [ ] (b) executor spread-gate rejection log admitted as the
                              IEX-side occurrence source — rejection-log schema,
                              match tolerance, and log admissibility frozen here: ____
Partition completeness:   [X] >= 98% observed/expected cycles per partition per feed,
                              max contiguous gap 10 min; feed_error counts toward the
                              denominator only (proposed)   [ ] adjusted to: ____
Free-space floor:         [X] max(10 GB, 20% of volume), checked before each write
                              cycle and before EOD/freeze; abort-and-alert on breach
                              (proposed)   [ ] adjusted to: ____________
Review-date anchor:       [X] 60-day clock from the FIRST ADMISSIBLE GOVERNED CAPTURE;
                              the RULE is frozen here; the concrete review date is
                              computed and stamped in the deployment record on the day
                              the first admissible partition freezes (owner 2026-08-17;
                              the date cannot exist before that capture does)
Durability (§6.4):        [X] S3 byte-for-byte mirror after verify (Recommended)
                          [ ] accept local-volume loss risk this cycle
Sampler cadence/retry:    [X] 60s cadence; per-feed error capture; continue on
                              transient failure; abort after 30 consecutive
                              failed cycles (proposed)   [ ] adjusted to: ____
Architecture (§7):        [X] Option 2A adopted by owner ruling 2026-08-15 — account-7 collector,
                              immutable local store on the AWS box, MDQ offline/read-only,
                              no MDQ Alpaca credentials; K2 deferred to Phase B.
Phase-A capture universe: [X] as proposed, MATERIALIZED as the frozen universe files
                              (50 symbols = BASE 22: SPY/QQQ/IWM + 11 sector SPDRs +
                              acct-7 transition set; + SAMPLE 28: top-28 by 60-session
                              avg dollar volume from Sharadar SEP as of 2026-06-12,
                              close >= $5, mechanical rule, no discretionary selection):
                              apps/backend/config/mdq_phase_a_universe.json
                                sha256 d6248e2b7055aec6ba77fc8ce4056840713830695a08ff61f4236cb780f77a45
                              apps/backend/config/mdq_phase_a_universe_symbols.json
                                (deployable --universe-file array)
                                sha256 0c57bd71c0b73565328ec27036c6573f11b87594acb49ca461458a7d947f88d4
Cross-program evidence:   [X] MDQ corpus ONLY (plan v0.6 §8 item 14) — the sealed
                              account-7 records (v1 FAIL c7b9371d…, v2 proof 67c400d3…,
                              CA diag a892edf4…) are citable context, never scored
                              toward K1/K6.
ATP value extraction:     [X] plan v0.7 §8 item 15 APPROVED as proposed — MOM-SIP-0,
                              CEE, SIP feature library, DISC-001, RANGE-SIP-OBS-001
                              per ATP_ValueExtraction_Spec_Pack_v0_1.md; observation-
                              only against frozen admissible partitions after G2;
                              priority order MOM-SIP-0 -> CEE -> feature library ->
                              DISC-001 -> RANGE-SIP-OBS-001 (Phase-A-supported
                              branches only; auction branch NOT EVALUABLE; no capture
                              expansion, no L1/L2, no reopened programs).
P-2 real-time tier:       [X] verified 2026-08-17 RTH — v2 proof (script sha
                              959c5399…, evidence sha 67c400d3…, R1–R4 all PASS);
                              v1 preserved as mechanical FAIL (c7b9371d…).
Registered by / date:     Jay Wang (owner) — 2026-08-17, authorization issued in
                          session ("Owner authorization — 2026-08-17", items B/E);
                          applied to this document by the developer session same day.
```

### 8.1 v0.8 addendum — value-extraction guardrails *(PROPOSED 2026-08-17, pending owner ratification)*

Plan v0.8 (§4.10.1–§4.10.3, §4.11) added three sign-off requirements after the §8 block above was signed. They are recorded here as **open decisions** — the signed block above is not edited. Proposed defaults follow the plan text.

```
Evidence firewall (4.10.1):   [X] RATIFIED (owner 2026-08-17) — value-extraction outputs (MOM-SIP-0, CEE,
                                  DISC-001, RANGE-SIP-OBS-001, feature library) are
                                  INADMISSIBLE to K1–K6; no K definition, threshold,
                                  tolerance, denominator, or evaluability clause may be
                                  revised once value-extraction work begins. A finding
                                  that a K definition was poorly chosen is preserved and
                                  versioned prospectively for a FUTURE cycle (the P-2
                                  precedent), never retuned mid-window.
Discovery ledger + holdout    [X] RATIFIED (owner 2026-08-17) — DISC-001/feature-library maintain an
(4.10.2):                         append-only discovery ledger (every condition examined,
                                  dated, disposition); any pre-registration drawn from
                                  exploration must cite its ledger entry and the number
                                  of conditions examined in that family. Holdout reserve
                                  MATERIALIZED (deterministic, zero discretion):
                                  apps/backend/config/mdq_phase_a_holdout.json
                                    sha256 6c6cf03a80598f54df89b599f2ffbbda09ea44af8f3596421d6c58104e2393bb
                                  symbol holdout (10/50, PRNG seeded by the universe
                                  list sha): AMZN EFA KMLM MSTR NBIS NOW TSLA XLK XLV XOM
                                  period holdout RULE: final 12 calendar days of the
                                  60-day window; dates stamp when the review clock stamps.
                                  Exploration never reads holdout symbols/period; a
                                  graduating hypothesis is evaluated on them once.
Verdict reachability (4.11):  [X] RATIFIED (owner 2026-08-17) — enumerated worst case UNDER THE CHOICES SIGNED
                                  ABOVE (item 14 = MDQ corpus only; K6 = option (a);
                                  G10 closed; Stage 0 awaiting G4; fills < N_min
                                  plausible while MR-002 holds): K1, K2, K4, K5, K6 can
                                  all be NOT EVALUABLE simultaneously, leaving GO
                                  reachable on K3 ALONE. Proposed floor: a GO verdict
                                  requires >= 2 of K1–K6 evaluated PASS; if fewer than 2
                                  criteria are evaluable at the review date, disposition
                                  is HOLD WITH A STATED EXTENSION — never a default
                                  Cancel on unevaluability, never a single-criterion GO.
Sequencing (4.10.3):          [X] Already ordered by the owner 2026-08-17 (authorization
                                  item E): MOM-SIP-0 -> CEE -> feature library (scoped to
                                  features MOM-SIP-0/CEE consume) -> DISC-001 ->
                                  RANGE-SIP-OBS-001; the latter two gated on the former
                                  producing output or an explicit owner time-box.
Ratified by / date:           Jay Wang (owner) — 2026-08-17, ratification issued in
                              session ("I ratify §8.1 in full, using all three proposed
                              defaults"); GO floor stated verbatim: GO requires at least
                              two of K1–K6 to be BOTH evaluable AND PASS; fewer than two
                              evaluable => HOLD with the required extension stated
                              explicitly. Holdout stays quarantined from discovery and
                              exploratory tuning until its governed release point.
                              Additive ratification only — the signed §8 block above is
                              not reopened. Applied by the developer session same day.
```

### 8.2 v1.0 correction set — owner rulings, 2026-08-18 *(three CORRECTIONS; one ADDITION — **signed 2026-08-19, §8.3**; see also §8.4, K5 discriminating status, signed 2026-08-20)*

Review of the governed text on 2026-08-18 — after the first scheduled governed capture was **refused by the deployed
fail-closed free-space guard** (09:25:02 EDT, `9G available < 10G floor`; zero cycles, no partition, **clock not
started**) and therefore while no admissible partition existed — surfaced four defects. The owner ruled on all four
the same day.

**Three of the four are consistency corrections**: they bind a definition this document left unbound, or align prose
that a later, more specific ratified decision had already superseded. They change **no** ratified threshold, and the
signed §8 block and ratified §8.1 block above are **not edited** — this subsection is additive, exactly as §8.1 was.
**The fourth adds a disposition that neither block ever defined** and is recorded here as **PENDING EXPLICIT OWNER
SIGN-OFF**, not as ratified.

#### Ruling 1 — `expected_cycles` denominator *(CORRECTION — binds `session_scope`; thresholds unchanged)*

§8 froze the **threshold** (≥ 98% completeness, ≤ 10-minute maximum contiguous gap) but left `session_scope` inside
`expected_cycles = f(session_scope, cadence, market calendar)` **unbound**. The only session interval this document
names is **04:00–16:00 ET**, which is the **EOD one-minute bar census scope** and **not** the quote-sampler
denominator; adopting it as the sampler denominator would mechanically fail every healthy partition. Frozen:

```text
sampler_start   = 09:25 America/New_York
sampler_end     = official NYSE close for that session, EXCLUSIVE
cadence         = 60 seconds
expected_cycles = count of scheduled cadence slots t such that
                  sampler_start <= t < sampler_end
```

⇒ **395** on a normal 16:00 close · **215** on a 13:00 early close · **0** on holidays and non-session days. The
**market calendar controls** early closes and non-trading days. The **98% completeness floor and the 10-minute
maximum contiguous gap are UNCHANGED**: the fix is the **definition**, not the threshold. The bar-census scope
remains 04:00–16:00 ET and remains the denominator on the bar side; `feed_error` records continue to count toward
the denominator and never the numerator.

**Related runtime ruling, recorded with it — scheduler drift is a runtime defect, not evidence against the floor.**
The collector's `cmd_sample` scheduled **fixed-delay** (it slept the cadence *after* doing the work), so the real
period was `60s + overhead` and a fully healthy capture drifted to roughly **383–389** cycles against a 395-slot
grid — it could therefore breach the 98% floor on a perfect network. That is **systematic scheduler drift, not
evidence that the 98% floor is too strict.** The runtime is being corrected to **fixed-rate scheduling against an
absolute monotonic deadline**, with **no burst / catch-up**, the session close checked **before** each cycle, and a
persisted `scheduled_slot_ts` / `slot_index` on every cycle so that observed cycles reproduce against the frozen
grid. **The threshold is not weakened to accommodate a defective runtime.** *(The runtime change is implementation
work owned elsewhere; it changes the collector code identity — see the program-start record §2.3 — and must be
re-stamped there before the first admissible capture.)*

#### Ruling 2 — the ANY-K conflict *(CORRECTION to stale prose; the ratified threshold is not reopened)*

§4 still read “Keep the subscription if **ANY** K criterion is met.” The later, specifically ratified §8.1 requires
**≥ 2 of K1–K6 both evaluable AND PASS**. **§8.1 controls.** §4 now reads equivalently to:

> **GO — retain the subscription only if at least two of K1–K6 are both EVALUABLE and PASS. A NOT EVALUABLE
> criterion neither passes nor fails and cannot contribute toward the GO floor.**

The §4 sentence was never updated when §8.1 was ratified; this is that update and nothing more. **No threshold, no
evaluability clause, and no signed block is reopened.**

#### Ruling 3 — the undefined verdict *(ADDITION — **SIGNED 2026-08-19**; full ruling at §8.3)*

The combined rules left **≥ 2 evaluable and exactly 1 PASS** genuinely undefined: not GO (needs ≥ 2 passes), not
STOP under the old “no K criterion met” wording (one criterion *was* met), and not covered by §8.1’s HOLD clause
(which addresses *fewer than two evaluable*). The completed table is in **§5**. Its first three rows restate
already-ratified decisions; **the fourth row assigns a disposition that did not previously exist**, which is why it
is recorded as proposed rather than applied:

```
Undefined-verdict disposition
(>= 2 evaluable, exactly 1 PASS):  [x] SIGNED - HOLD, exactly one additional period
                                   [ ] adjusted to: ____________
                                   Status: SIGNED 2026-08-19, BEFORE any exploratory
                                   read of the corpus and therefore before the 8.1
                                   evidence firewall closed the ability to revise a
                                   verdict/evaluability clause. Rows 1-3 of the
                                   section 5 table are ratified restatements; THIS row
                                   was an addition and is ratified by the signature
                                   below and by section 8.3, not by its presence in
                                   that table.
                                   The signed ruling adds two invocation requirements
                                   to EVERY hold and one expiry rule; see section 8.3.
Signed by / date:                  Jay Wang (owner) — 2026-08-19
```

#### Ruling 4 — holdout boundary and exploration embargo *(CORRECTION — makes the ratified §8.1 rule arithmetically exact)*

§8.1 ratified the period-holdout **rule** (“final 12 calendar days of the 60-day window”) and deferred the **dates**
to the clock stamp. It did not state the offset arithmetic, and the rule as written admits two readings that differ
by a day at each end. Frozen:

```text
review_start_date    = session_date of the first admissible governed capture
review_end_exclusive = review_start_date + 60 calendar days
period_holdout_start = review_start_date + 48 calendar days

period holdout       = session_date >= period_holdout_start
                       AND session_date <  review_end_exclusive
```

⇒ the **review window is offsets 0–59** and the **holdout is offsets 48–59 — exactly 12 calendar dates**.

**Do not slide the boundary for weekends or holidays.** A non-session date inside the holdout simply contains no
trading partition. Sliding the boundary would silently convert “the final 20% of the window” into “the final 12
**trading sessions**” — a different rule, and a materially larger holdout than the one §8.1 ratified.

Exploration embargo, stated as the predicate that governs every value-extraction read:

```text
exploratory_access_allowed = symbol NOT IN holdout_symbols
                             AND session_date < period_holdout_start
```

⇒ the **10 holdout symbols** (§8.1: AMZN EFA KMLM MSTR NBIS NOW TSLA XLK XLV XOM) are quarantined for the **entire**
window, and **every** symbol is quarantined during the **final 12 calendar dates**. The symbol holdout, its draw
rule, and the artifact sha `6c6cf03a…` are unchanged; the holdout artifact is **not** rewritten with the dates (that
would change its hash and break the §8.1 binding) — the stamped dates live in the program-start record.

#### Applied by / status

```
Rulings 1, 2, 4 (corrections):  APPLIED to this document 2026-08-18 by the developer
                                session, as owner-stated. Additive only; the signed
                                section 8 block and the ratified section 8.1 block are
                                untouched.
Ruling 3 (addition):            SIGNED 2026-08-19 and APPLIED. The sign-off stanza
                                above is completed; the full ruling, including the two
                                invocation requirements it adds to every HOLD and the
                                expiry rule, is at section 8.3.
Ruled by / date:                Jay Wang (owner) — 2026-08-18, rulings issued in session.
```

### 8.3 Undefined-verdict disposition — SIGNED, 2026-08-19

**Status: SIGNED.** Signed **2026-08-19**, the same day D0 was established and **before any exploratory read of
the corpus**. That timing is load-bearing, not incidental: once exploration touches the corpus, §8.1’s evidence
firewall forbids revising a verdict or evaluability clause, so an unsigned gap here would have become *unfixable*
rather than merely open. This subsection is **additive**. The signed §8 block and the ratified §8.1 block are
**not edited**, exactly as §8.1 and §8.2 were additive before it.

#### 8.3.1 The complete disposition matrix

| Evaluable | PASS | Disposition |
|---|---|---|
| < 2 | any | **HOLD** — exactly one additional period |
| ≥ 2 | 0 | **STOP** |
| ≥ 2 | **exactly 1** | **HOLD** — exactly one additional period |
| ≥ 2 | ≥ 2 | **GO** |

The matrix is **total and mutually exclusive**: PASS ⊆ EVALUABLE, so the `< 2 evaluable` row can only ever carry
0 or 1 PASS, and no combination falls outside the four rows.

**What was already ratified, and what this signature adds.** Rows 1, 2 and 4 restate existing decisions — rows 1
and 4 are the §8.1 GO floor verbatim, row 2 is C1 read with that floor. **Row 3 is the addition.** The combined
rules left `≥ 2 evaluable and exactly 1 PASS` genuinely undefined: not GO (which needs ≥ 2 passes), not STOP under
the old “no K criterion met” wording (one criterion *was* met), and not covered by §8.1’s HOLD clause (which
addresses *fewer than two evaluable*).

**Why HOLD and not GO or STOP.** One passing criterion is below the already-ratified ≥ 2-PASS GO floor, so GO would
weaken a ratified threshold. But one PASS is also materially different from zero PASS, so STOP would discard
potentially useful evidence prematurely. **HOLD is the only disposition that preserves both rules without weakening
either one.**

#### 8.3.2 Invocation requirements — applies to EVERY HOLD, both rows

§5 already defines HOLD as *“extend **exactly one** additional period, for a named reason stated at the verdict.”*
That rule is **unchanged and is not reopened**. This signature **adds** two requirements to it:

1. **The extension duration** must be stated at the moment HOLD is invoked.
2. **The next adjudication date** must be stated at the moment HOLD is invoked.

Both are stated **when HOLD is invoked**, from what is known then — they are **not** pre-set here from future data,
and they are **not** to be chosen after seeing the evidence that triggered the HOLD.

These requirements bind **both** HOLD rows identically. Bounding only the `exactly 1 PASS` row would have left
`< 2 evaluable` as the likelier indefinite path, since evaluability can remain low indefinitely without anyone
having to decide anything.

#### 8.3.3 Expiry — what "exactly one" actually means

At the stated next adjudication date the matrix is re-applied **once**:

| Outcome at re-adjudication | Disposition |
|---|---|
| Cell improved to `≥ 2 evaluable, ≥ 2 PASS` | **GO** |
| Cell fell to `≥ 2 evaluable, 0 PASS` | **STOP** |
| **The same triggering cell still applies** | **STOP** |

**No second HOLD is permitted for the same review sequence.** Without this rule “exactly one additional period”
would be unenforceable: `HOLD → HOLD` would be reachable, and HOLD would degrade into an indefinite
subscription-renewal mechanism — renewing the subscription by never quite deciding. The purpose of the bound is
that the decision is **forced**, not deferred.

#### 8.3.4 Scope — what this signature does not do

It does **not** amend, reopen, or reinterpret the signed §8 block or the ratified §8.1 block. It does **not** adjust
any K-criterion, threshold, tolerance, denominator, or evaluability clause — in particular the ≥ 2-PASS GO floor
and the C1/STOP threshold are untouched. It does **not** decide any actual verdict: no K criterion has been
evaluated, and the review date is 2026-10-18. It settles only **which disposition follows from which review
result**, plus the invocation and expiry mechanics above.

#### 8.3.5 Effect on the exploration embargo

The embargo existed because this row was unsigned and §7.2 forbids revising a disposition rule once exploration
begins. **With this ruling signed and landed, that specific blocker is cleared** and the planned value-extraction
sequence may begin in the owner’s priority order (MOM-SIP-0 → CEE → feature library → DISC-001 → RANGE-SIP-OBS).

All other constraints are **unchanged**: the two-way evidence firewall stands, value-extraction outputs remain
**inadmissible** to K1–K6, no K criterion may be revised once exploration begins, and **exploration never reads the
holdout** — 10 of 50 symbols (AMZN EFA KMLM MSTR NBIS NOW TSLA XLK XLV XOM) over `[2026-10-06, 2026-10-18)`.
Capture continues normally on the governed schedule.

```
Undefined-verdict disposition:  SIGNED - HOLD, exactly one additional period
Invocation requirements:        SIGNED - duration + next adjudication date,
                                stated at invocation, both HOLD rows
Expiry rule:                    SIGNED - repeat of the triggering cell => STOP;
                                no second HOLD in the same review sequence
Signed before exploration:      YES - no exploratory read has occurred
Signed by / date:               Jay Wang (owner) — 2026-08-19
```

---

### 8.4 K5 discriminating status — SIGNED, 2026-08-20

**Status: SIGNED.** Signed **2026-08-20**, **before any exploratory read of the corpus** and therefore before
§8.1's evidence firewall forecloses revising a verdict or evaluability clause. This subsection is
**additive**: the signed §8 block, the ratified §8.1 block, §8.2 and §8.3 are **not edited**.

This is the mirror image of the §4.11 verdict-reachability problem. §4.11 protected against criteria that
can never be **evaluated**. K5 is a criterion that can never **fail** — and an auto-passing criterion is the
more dangerous of the two, because it looks like evidence and **counts toward the ratified GO floor**.

#### 8.4.1 Determination — made from the frozen definition, before any coverage result

**K5 as frozen cannot return FAIL for its intended coverage question.** Under the frozen population rule,
fills without a valid matched quote are excluded from **both** numerator and denominator; for the fills that
remain, the coverage numerator and denominator are therefore **structurally equivalent except for
computation/integrity failures**. The K5 coverage ratio consequently approaches **100% by construction on any
admissible corpus**.

**This determination is made from the frozen definition before any governed K5 coverage result is examined.**
That ordering is the substance of the ruling, not a formality: the same statement made in October, after
results exist, would be a post-hoc judgement about whether a criterion "really" discriminates — arguable in
whichever direction happened to be convenient.

#### 8.4.2 Effect on reporting and on the GO floor

1. **K5 is still calculated and reported exactly as frozen.** No result is suppressed and no metric is
   recomputed under a different rule.
2. **If `N_min` is not met, K5 is NOT EVALUABLE** — unchanged from §4.3.
3. **If `N_min` is met and the frozen computation succeeds, K5 may mechanically report PASS**, and that
   result **remains a K5 PASS in the evidence record**.
4. **That non-discriminating PASS does not count toward the ≥2 independent evaluable-and-PASS criteria
   required for GO** (§8.1).

⭐ The historical result is **preserved, not rewritten.** K5's mechanical PASS stands on the record as a K5
PASS; only its *contribution to the GO floor* is qualified. This is the P-2 precedent applied again: preserve
the run, mark the criterion on its own terms, version forward.

#### 8.4.3 What is NOT changed

**No K5 threshold, denominator, matching rule, `N_min`, evaluability clause, or metric definition is
changed.** Specifically unchanged: the 90% coverage threshold; `N_min` = 50; the R2 quote-match rule
(`0 <= ref_ts - cycle_ts <= 5s`); the population definition (all paper fills, Phase-A symbols only); the
exclusion of no-quote fills from numerator and denominator; and the NOT-EVALUABLE-below-`N_min` semantics.

§4.10.1 forbids revising a K definition once value-extraction work begins, and the R2 ruling was correctly
frozen **before** coverage was seen. Reopening either would be exactly the post-hoc move the firewall exists
to stop. What §8.4 decides is a **verdict-clause** question — how a PASS is *counted* toward the GO floor —
which is the same class as §8.3's ruling 3.

#### 8.4.4 Consequence for the verdict, stated plainly

With K2 NOT EVALUABLE (no G10), K4 NOT EVALUABLE (no in-window Stage-0 run), K6 NOT EVALUABLE absent a
captured IEX stub occurrence, and K5's PASS now non-contributing, **the GO floor rests on K1 and K3**. If
only one of those is both evaluable and PASS, the disposition is **HOLD with one stated extension** under
§8.3's matrix. That is a real outcome the ratified rules already provide for — not a failure of the process,
and not a reason to relax a threshold.

#### 8.4.5 Sign-off

```
K5 discriminating status:       SIGNED - K5 as frozen CANNOT return FAIL for the
                                coverage question (numerator == denominator by
                                construction after the no-quote exclusion)
Determination timing:           SIGNED - determined from the frozen definition
                                BEFORE any governed K5 coverage result examined
Reporting:                      SIGNED - K5 still computed and reported exactly
                                as frozen; a mechanical PASS remains a K5 PASS
                                in the evidence record
GO-floor contribution:          SIGNED - a non-discriminating PASS does NOT count
                                toward the >=2 independent evaluable-and-PASS
                                criteria required for GO
Definitions changed:            NONE - threshold, denominator, matching rule,
                                N_min, evaluability clause and metric definition
                                are all unchanged
Signed before exploration:      YES - no exploratory read has occurred
Signed by / date:               Jay Wang (owner) — 2026-08-20
```

---

## 9. Authority

Planning/qualification governance only. If this document conflicts with a frozen pre-registration, sealed verdict, owner ruling, hash-bound design, ADR, or promotion gate, the governed program artifact controls. MR-002 HOLD and the GAPPER v2.1.1 §9 sequencing are unaffected by anything here.
