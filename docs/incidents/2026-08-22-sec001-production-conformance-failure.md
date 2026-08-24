# Incident — SEC-001 production conformance failure (account 5 / `sector-rotation` id=7)

**Status: OPEN — containment authorized, execution blocked on credentials (see §8).**
Opened 2026-08-22. Account/book: user 5 / `sector-rotation` (id=7) / Alpaca paper account 5.
Severity: **production nonconformance with evidence contamination** — no capital loss event, but
~8 weeks of accrued "SEC-001" production evidence describes a strategy that was never SEC-001.

## One-line finding

Account 5 has never run frozen SEC-001. The promotion shipped a different signal *and* a different
construction, and the frozen construction could not have run under the production risk envelope
even if it had been copied correctly.

> ### ⚠ Repairing SEC-001 does not repair its historical evidence.
>
> The eight weeks of account-5 accrual are not "SEC-001 results that need a correction factor" —
> they are measurements of a different book. Correcting the implementation retrospectively cannot
> rehabilitate them. **Any future SEC-001 promotion evidence starts from zero**, after an approved
> V3 activation (G1, G6).

> ### ✅ The time-critical risk is closed
>
> Strategy 7 was stopped through the authenticated UI at **2026-08-22 15:46:06 UTC** and the
> unregister was independently verified at 15:51 (§8.2): status `IDLE`, APScheduler job
> `strategy:7:on_bar` removed, audit row 7324 hash-verified, run 765 closed. **The Monday
> 2026-08-24 10:24 ET rebalance will not fire.**
>
> Account 5's 99 positions ($99,046) remain **intentionally untouched** until Monday's governed
> flatten (C5b). Nothing in §9 or §10 begins until C6.

## 1. What is deployed vs what is frozen

| | Frozen SEC-001 (V2) | Deployed since 2026-06-24 |
|---|---|---|
| Signal | 252 / **21** (12-1 sector momentum) | 252 / **0** |
| Construction | 1/K sector sleeve, `(1/K)·(1/n_sector)` per name | `equity / len(target)` — equal per **name** |
| Sector neutrality | Yes, by construction | **Absent** |

**Authority for the frozen values** (three independent, agreeing sources):

- `apps/backend/app/research/factor_lab/configs.py` — `SEC_001.factor_params = {"lookback_days": 252,
  "skip_days": 21, "k": 3, "k_band": [2, 4]}`, philosophy *"Sector-neutral top-K equal-weight baskets
  on 12-1 sector momentum"*.
- `apps/backend/scripts/sector_rotation_v2_research.py` — `SKIP_DAYS = 21`; `basket_weights()`
  documents *"A name's weight = (1/K)*(1/n_sector)"*.
- `apps/backend/app/factor_data/factors/sector.py` — `DEFAULT_SKIP_DAYS = 21` and
  `sector_basket_weights()`, the factor-library home of the promoted construction.

## 2. Measured effect on the live book

Reconstructed from the live factor store on `i-084f47fe4e69192e9` and matched against the actual
`positions` rows for account 5:

```
HELD (live positions):      99
PREDICTED deployed 252/0 :  99   [Technology, Energy, Industrials]
PREDICTED frozen  252/21 :  93   [Technology, Industrials, Real Estate]

held == deployed 252/0   ->  True    (held-pred = [],  pred-held = [])
held == frozen  252/21   ->  False   (extra: COP CVX DVN SHEL SLB VLO XOM · missing: WELL)
```

This is an exact 99/99 set identity, not a correlation. Sector weights actually carried, 2026-08-17:

| Sector | Deployed | Frozen intent |
|---|---|---|
| Technology | **70.5%** | 33.3% |
| Industrials | 21.9% | 33.3% |
| Energy | 7.6% | 33.3% (not held at all under the frozen signal) |
| Real Estate | 0% | 33.3% (`WELL`) |

Technology is **2.1× its intended weight**. The signal defect independently changes *selection*: on
both 2026-08-10 and 2026-08-17 the deployed 252/0 ranking selects **Energy** third while the frozen
252/21 ranking selects **Real Estate**.

## 3. Root cause

`git blame` places **both** defects in `8ed2975` (PR #242, 2026-06-24) — the SEC-001 Capability
Promotion itself. Not later drift. The defective line carries its own explanation:

```python
"sector_momentum_lookback_days": 252,  # 12-month, matching Momentum 252/0
"sector_momentum_skip_days": 0,        # no skip (matching Momentum)
```

under a block comment claiming *"all from sector_rotation_v2_research.py"*, which is false.

The comment's premise about Momentum is **correct** — `registry.py::_momentum` defaults
`skip_days = 0` and `MOM_001.factor_params` does not override it, so MOM-001 genuinely is 252/0, and
`momentum_portfolio.py` is conforming. The error is narrower and more instructive: **SEC-001
explicitly overrides that shared default to 21, and the promotion did not notice the override.**

The error is self-evidencing in three places:

1. `_select_targets`'s own docstring asserts the sizing *"gives each name ≈ (1/K)·(1/n_sector) of the
   book"* — `_apply_targets` does not do that. The code contradicts its own docstring.
2. `tests/strategies/test_sector_rotation_template.py` **pins** the defect: a test docstring reading
   *"The validated SEC-001 V2 parameters must not silently drift"* asserts `skip_days == 0`, and
   `test_equal_weight_within_book` asserts `investable / n_names`.
3. The session doc and the project memory both recorded "(252/0)" as the research value, propagating
   the error beyond the code.

**Not a cause:** universe staleness. The registered 199-name list overlaps `universe_asof(n=200)`
190/200 at 2026-08-17 with near-identical sector distributions. The universe is conforming.

## 4. Historical blast radius — CLOSED

The audit log settles the remaining question of an earlier DB override. Every `STRATEGY_UPDATED` row
for strategy 7 that carries a params payload — **6 rows, 2026-06-29 through 2026-07-07** — records
`"sector_momentum_skip_days": 0`. A whole-log scan for `skip_days` / `sector_momentum` returns only
strategy 7 (always `0`) and strategy 9 / combined-book (always `21`, correctly, for PORT-001).

⇒ **No period of conforming operation has ever existed.** The prior "likely affected from 6/30" is
upgraded to **confirmed for every rebalance since inception**. Nothing remains pending on G2.

## 5. Three linked nonconformances (one incident, not three bugs)

1. **Signal conformance failure** — 252/0 deployed instead of frozen 252/21.
2. **Construction conformance failure** — equal-per-name deployed instead of sector-neutral sleeves.
3. **Promotion feasibility failure** — the promotion never demonstrated that frozen V2 could coexist
   with the production `max_position_pct = 0.10` cap.

The third is the load-bearing one: **correcting (1) and (2) alone does not close this incident.**

## 6. Why the frozen construction is not deployable — mathematical, not implementational

For frozen K=3 with equal weight inside a 1/K sleeve, a name's weight is `1/(3·n_s)`. Requiring
`1/(3·n_s) <= 0.10` gives:

```
n_s  >=  ceil( 1 / (K * position_cap) )  =  ceil( 1 / (3 * 0.10) )  =  4
```

Every selected sector needs **>= 4 eligible names** to satisfy all five conditions simultaneously:
K=3 · 33.33% per sector · equal weight within sector · <=10% per name · 100% invested.

At 2026-08-17 the frozen signal selects **Real Estate with n=1** (`WELL`) in the registered universe
(n=2 in `universe_asof(200)` — 16.67% per name, still a breach). The V2 research backtest applied no
per-name cap; production does. **No implementation can satisfy all five conditions.** This is not a
coding problem, and the required breadth floor `N_min = 4` is *derived from the production
constraint*, not tuned from the August observation.

## 7. Owner decisions (2026-08-22)

**The production risk cap stays at 10%. The scientific reference stays 252/21, K=3, 1/3 per sector,
equal-weight within sector.** An unrepresentable target means the strategy is **not deployable**
under the current risk envelope; account 5 is therefore **contained, not modified into an
unresearched hybrid**.

| Option | Decision | Reason |
|---|---|---|
| K={2,4} failover | **Reject** | {2,4} was a robustness band, not an adaptive production rule. K=4 doesn't fix a one-name sector (25% > 10%); K=2 is worse (50%). |
| Minimum sector breadth | **Research as V3** | The only option preserving K=3, sector neutrality, full investment and the 10% cap simultaneously. Use derived `N_min = 4`. |
| Raise the position cap | **Reject** | A one-name sector needs a 33.3% single-name limit; two names need 16.7%. Materially weakens the risk envelope to accommodate a research construction. |
| Accept partial investment | **Reject for SEC-001** | Produces ~33.3/33.3/10 + 23.3% cash. Cash becomes an unintended fourth sleeve; the book is neither sector-neutral nor equivalent to V2. Researchable later, but it is **not** the conformance repair. |

## 8. Containment — state as of 2026-08-22 13:30 UTC

~~**Deadline: the next scheduled rebalance is Monday 2026-08-24 10:24 ET (14:24 UTC).**~~
**RESOLVED 2026-08-22 15:46:06 UTC.** Strategy 7 was `status=PAPER` with `strategy_runs` id=765 open
since 2026-08-21 22:57 and a `24 10 * * mon` schedule evaluated in `America/New_York`
(`engine.py::_STRATEGY_SCHEDULE_TZ`) — i.e. it would have executed during RTH. The authenticated
stop removed that job; §8.2 records the independent proof. No further 252/0 rebalance can occur.

Containment runs in this order. **Nothing in §9 or §10 begins until C6 is complete.**

| # | Step | When | State |
|---|---|---|---|
| C1 | Forensic snapshot sealed (pre-containment) | done | ✅ **DONE** |
| C2 | Mark accrued SEC-001 production evidence non-conforming | done | ✅ recorded by this document (G1) |
| C5 | Forensic snapshot into governed S3 custody + manifest | done | ✅ **DONE** (§8.1) |
| **C3** | **Stop strategy 7 via the authenticated UI/API** | 2026-08-22 15:46:06 UTC | ✅ **DONE** |
| C4 | Independent proof `Engine.unregister` removed the scheduled job: strategy status, scheduler/job state, audit row, run closure | 2026-08-22 15:51 UTC | ✅ **DONE** (§8.2) |
| C5b | Flatten account 5 via `flatten_account.py` on the authenticated path | **Mon 08-24 during RTH only** | ⬜ pending C3 |
| C6 | Verify 0 positions + no open orders; capture the **post-containment snapshot** into the same incident prefix as a *separate* manifest entry | after C5b | ⬜ pending C5b |

**C5b must not be run while the market is closed.** `flatten_account.py` logs `MARKET_SESSION_CLOSED`
and **exits 0** — a successful-looking run that flattens nothing. C1 and C6 together form the
before/after custody pair for this incident.

**C1 evidence, sealed on the box:**

```
path   : /opt/workbench/data/sec001_conformance_forensic_20260822T132918Z.json
sha256 : 170e3878b1960f96a01cdfa2d09de6699f3a07963e2ed64bf512fcad7eeab953
bytes  : 1317829
content: strategy-7 row · account/user 5 · 99 positions · 396 orders · fills ·
         161 strategy-7 audit rows (incl. row_hash/prev_hash) · 1846 other user-5 audit rows ·
         both reconstructed books for 08-10 and 08-17 · frozen spec of record

deployed code identity (runtime blobs, re-read this session — never inherited):
  strategies_user/templates/sector_rotation.py
      5eaba72c6b358e741695d136bd89dad86a02db684fd24fdd7337ddfe062cf1fe  (22421 B)
  app/factor_data/factors/sector.py
      7e7f6cc4895bb7a52ecb92209e0ab46d1323fb729ced9d25389b9c475e52df46
```

### 8.1 Custody manifest — governed S3 (C5 COMPLETE)

The forward-validation witness bucket was **deliberately not used**: ADR 0047 makes
`workbench-witness-forward-validation-219024422756` a dedicated boundary with exactly two governed
prefixes (`witness/`, `preflight/`), and that separation is load-bearing. A live-account survey
confirmed no general incident/evidence bucket existed — the account's pattern is one dedicated
bucket per program (`workbench-mr002-sealed`, `adr0043-ws5-evidence`, `workbench-step4c-proof`).
A dedicated bucket was therefore created rather than guessed at.

```
bucket        : workbench-evidence-incidents-219024422756   (us-east-1, created 2026-08-22)
versioning    : Enabled          object-lock : COMPLIANCE, default retention 2555 days (7 y)
encryption    : AES256 (SSE-S3)  public access: all four blocks true
```

This mirrors the ADR-0047 witness-bucket standard (COMPLIANCE/2555) — a deliberate escalation above
the MR-002 / ADR-0043 evidence tier, which is versioning + SSE + PAB with **no** Object Lock.

| Field | Value |
|---|---|
| Key | `sec001/2026-08-22/sec001_conformance_forensic_20260822T132918Z.json` |
| VersionId | `ic_dggadrRrNWy97jpr1GuG2SjfVLrT3` |
| ETag | `96a9127df0bc7e32a5627e125da0482c` |
| SHA-256 | `170e3878b1960f96a01cdfa2d09de6699f3a07963e2ed64bf512fcad7eeab953` |
| Size | 1,317,829 B |
| Object-Lock mode | COMPLIANCE |
| Retain until | **2033-08-20T15:25:53.542Z** |
| SSE | AES256 |

**Integrity verified, not assumed:** S3's server-computed `ChecksumSHA256`
(`Fw44eLGWD5agHN+i0J3maZ86B5Y+LtZL9RL8rX7quVM=`) decodes to exactly the locally computed digest
above. The stored object is byte-identical to the sealed original.

**Access boundary.** The paper host (`workbench-paper-InstanceRole-4P2Tvq7FaG1E`) is granted
`s3:PutObject` on this bucket and explicitly **denied** `DeleteObject`, `DeleteObjectVersion`,
`BypassGovernanceRetention`, `PutObjectRetention`, `PutObjectLegalHold`, `PutBucketPolicy`,
`DeleteBucketPolicy`, `PutLifecycleConfiguration`, `PutBucketVersioning` — write-only, per the
containment ruling. Proven by execution rather than by reading the policy:

| Control | Result |
|---|---|
| N1 host deletes object | ❌ AccessDenied — *explicit deny in a resource-based policy* |
| N2 host deletes the version | ❌ AccessDenied — *explicit deny in a resource-based policy* |
| N3 host shortens retention | ❌ AccessDenied — *explicit deny in a resource-based policy* |
| N4 host rewrites/deletes the bucket policy | ❌ AccessDenied — *explicit deny in a resource-based policy* |
| P1 host writes a new object | ✅ succeeds — the write path stays open |

⚠ **Disclosure — control artifact in the evidence prefix.** The P1 positive control was written to
`sec001/2026-08-22/_writeprobe.txt` (6 B, VersionId `ySyNNIhPFraMKjiIWqkmxaMZkWhzXlXg`), inside the
evidence prefix rather than a separate controls prefix. Because the bucket default retention is
COMPLIANCE, **it cannot be removed by anyone, including the account root, until 2033-08-20** — it is
a permanent, immaterial resident of this prefix. It is recorded here so a future reader of the
prefix listing has a complete account of its contents. Future write probes belong outside the
evidence prefix.

### 8.2 C4 — independent verification that the stop propagated (read-only)

Verified 2026-08-22 15:51:24 UTC against the live host, DB opened `mode=ro`, no positions touched.
All four checks pass. **The Monday 10:24 ET rebalance risk is removed.**

| # | Check | Result |
|---|---|---|
| 1 | Strategy state | ✅ `status = IDLE` (was PAPER), `updated_at 2026-08-22 15:46:06.736258` |
| 2 | Engine + scheduler | ✅ `Removed job strategy:7:on_bar`; `strategy_unregistered` `reason=user_stop` via `POST /api/v1/strategies/7/stop`, `request_id 4bc466c5-424a-430b-b9b5-d14dd0b630d4`, `2026-08-22T15:46:06.750196Z`. No `strategy_remove_job_failed`. No overlay job existed to remove (`overlay_job_id = None` for this template) |
| 3 | Audit evidence | ✅ row **7324** — see below |
| 4 | Run closure | ✅ run **765** closed `2026-08-22 15:46:06.736258`, `status=IDLE`; `max(run_id)` for strategy 7 **is 765** — no successor run was created |

**Preserved audit evidence (chain verified by recomputation, not by trust):**

```
audit_log id : 7324
ts           : 2026-08-22 15:46:06.741210
action       : STRATEGY_UNREGISTERED      actor: user:5     payload: {"reason": "user_stop"}
row_hash     : a7ef1ce4656c8fd9d487a4c697d2478e34aeae7020c0dd335f0b5e53046599a1
prev_hash    : a14c689fb53e671c71d87fafe92e68f9e7543305fc03c0a87ab8bba92f352a66
```

`compute_row_hash(...)` re-run over the stored row reproduces `row_hash` **exactly**. `prev_hash`
equals the `row_hash` of id **7322** (`STRATEGY_REGISTERED`, 2026-08-21 22:57:43.074807), the
preceding row in **user 5's** chain — the chains are per-user, so a global-ordering check would have
reported a false break. Row 7324 is currently the tip of that chain.

Timestamps are internally coherent with a single `unregister` call in the order the code performs
them: run closed + status set `…06.736258` → audit row `…06.741210` → commit → engine log
`…06.750196`.

**Containment survives a reboot** (derived from code, not tested): `resume_on_boot` only resumes
strategies in `ENGINE_RUNNABLE_STATUSES`. Strategy 7 is now `IDLE`, so a backend restart will not
re-arm it — the boot count should drop from `resumed 3` to `resumed 2`.

**Position safety confirmed unchanged:** 99 positions, $99,046 market value, **0** non-terminal
orders. C4 touched nothing; the flatten remains Monday's governed action.

#### Two corrections to the C4 criteria as originally worded

1. **There is no `STRATEGY_STOPPED` row, and there never will be.** `POST /strategies/{id}/stop`
   writes no audit row itself; `Engine.unregister` writes the row, with action
   **`STRATEGY_UNREGISTERED`**. The `AuditAction.STRATEGY_STOPPED` enum member exists but **no code
   path emits it** — a whole-DB scan finds zero such rows. The audit obligation is met; only the
   action name differs. Anyone auditing a stop must query `STRATEGY_UNREGISTERED`.

2. ⚠ **"No open `strategy_run` for strategy 7" is unachievable and must not gate C4.** Strategy 7
   has **130** rows with `ended_at IS NULL`, dating to 2026-06-24. This is **systemic, not specific
   to this stop or this strategy**:

   | strategy | open runs | strategy | open runs |
   |---|---|---|---|
   | 7 | 130 | 2 | 103 |
   | 8 | 129 | 9 | 75 |
   | 1 | 128 | 4 / 5 | 55 / 54 |

   Platform-wide: **677 open vs 84 closed** — ~89% of all `strategy_run` rows are never closed.
   Each backend restart's `resume_on_boot` opens a new run without closing the previous one, and
   `unregister` closes only the run the engine currently tracks (`running.run_id`). The meaningful
   criterion — and the one verified above — is **"the run of the current engine epoch is closed and
   no successor run exists."**

   This is a **pre-existing observability defect, not a containment failure**, but it is not
   cosmetic: any "is this strategy running?" question answered from open `strategy_run` rows is
   wrong for every strategy on the platform. Logged as follow-on work; it does **not** block this
   incident.

**Why C5b is blocked.** Both the stop (`POST /strategies/{id}/stop`) and the flatten
(`scripts/flatten_account.py`) drive the authenticated HTTP API — deliberately, so every sell goes
through the OrderRouter and is risk-gated and audited (ADR 0002). They require user 5's password and
TOTP. The June-era shared credential is presumed invalid after the 2026-07-28 rotation, and there is
no compliant transport for the agent to receive the secret. **Do not** work around this by editing
`strategies.status` in the DB: it would bypass the audit log *and* would not work, because the engine
holds the APScheduler job in memory — only `Engine.unregister` via the API actually cancels it.

## 9. Code repair — must fail closed

1. `sector_momentum_skip_days`: `0` → `21`.
2. Replace the duplicated sizing math with the already-validated
   `app/factor_data/factors/sector.py::sector_basket_weights()` rather than re-implementing it.
3. Remove/correct the tests that falsely pin 252/0 and equal-name weighting, and the docstring that
   claims a construction the code does not implement.
4. **Add a pre-trade representability gate:**

   ```
   frozen target -> risk-envelope feasibility check -> orders

   if max(frozen target weight) > max_position_pct:
        SEC001_TARGET_INFEASIBLE -> no rebalance orders
   ```

   **Not** `target -> silently cap -> invest remainder`, and **not** `target -> dynamically change K`.
   Either operation silently creates an unregistered strategy. Since account 5 will already be flat,
   fail-closed leaves it in cash rather than carrying a stale part-valid sector book.

## 10. Remediation research — SEC-001 V3, not SEC-002

**SEC-001 V3 — Risk-Compatible Sector Baskets.** The economic hypothesis is unchanged (12-1 sector
momentum); V2 was itself a construction revision, and this is another. Selection rule: rank sectors
with the frozen 252/21 signal, but **only sectors able to implement an equal sector sleeve without
violating the pre-existing position-risk limit are eligible** (`N_min = ceil(1/(K * position_cap)) = 4`,
derived — *not* tuned from August).

Because this changes selection, **the historical SEC-001 verdict cannot be inherited.** V3 must run
through Factor Lab over the original 2000-01-01 → 2026-06-12 PIT window and be compared against V2.

## 11. Closure gates

| Gate | Requirement | State |
|---|---|---|
| **G1** | **Evidence quarantine** — all account-5 SEC-001 continuous evidence **from inception** is nonconforming and carries **zero credit** toward SEC-001 promotion | ✅ recorded here |
| **G2** | **Historical blast radius** — **CLOSED.** Every rebalance since 2026-06-30 is affected; **no conforming paper interval ever existed** | ✅ **CLOSED** (§4) |
| **G3** | **Mechanical conformance repair** — 252/21 + the validated basket-weight implementation + corrected anti-drift tests | ⬜ open |
| **G4** | **Representability fail-closed** — a frozen target violating the 10% name cap generates **no rebalance orders** | ⬜ open |
| **G5** | **SEC-001 V3 research** — mechanically derived `n_s >= 4` eligibility studied **prospectively** against V2 | ⬜ open |
| **G6** | **Fresh paper accrual** — any future promotion evidence starts **from zero** after an approved V3 activation. The prior eight weeks **cannot be rehabilitated** by retrospectively correcting the implementation | ⬜ open |

## 12. Governance note

This is a **conformance repair**, not a retune. The corrected parameters were frozen by the archived
research long before the 2026-08-10 → 08-21 drawdown, so that P&L may **not** be cited as
justification for them. Symmetrically, the drawdown may **not** be attributed to rotation, holding
period, name selection, or market direction: a 70% Technology book is a different object from a 33%
sleeve, and no attribution over this period describes SEC-001.

---

## 13. Pre-RTH verification, 2026-08-24 (before the 10:24 ET schedule slot)

Read-only against the live box `i-084f47fe4e69192e9` via SSM. Every line below was measured this
session; **no deployed identity was inherited from §8.**

### 13.1 Containment holds — the 10:24 ET slot cannot fire

| Check | Measured |
|---|---|
| `strategies.id=7` | `status=IDLE`, `updated_at=2026-08-22 15:46:06.736258` (unchanged since C3) |
| `resume_on_boot_complete` @ `2026-08-24T10:09:24Z` | **attempted 2 / resumed 2** — was 3 pre-containment |
| Prior boot @ `2026-08-23T20:18:24Z` | attempted 2 / resumed 2 |
| `strategy:7` in scheduler log this epoch | **zero occurrences**; no `Added job strategy:*` lines |
| `strategy_runs` | `max(id)=765`, `ended_at=2026-08-22 15:46:06.736258`; no successor |
| Strategies for user 5 | exactly one (id=7) |
| Orders acct 5 | 396 total, **0 non-terminal**, last created `2026-08-17`; all `source_type=STRATEGY, source_id=7` |
| Audit | row **7324** `STRATEGY_UNREGISTERED` still the last strategy-7 event |

⭐ Containment has now survived **two** backend restarts (08-23 20:18Z, 08-24 10:09Z). The
`attempted 3 → 2` drop is the positive signal: the resume set itself shrank by exactly strategy 7.

### 13.2 CORRECTION — §8's "deployed code identity" is a CRLF artifact, not a different build

§8 records the C1 deployed blobs as `5eaba72c…` (22421 B) and `7e7f6cc4…` (7165 B). **No file on the
running system hashes to either value.** Measured today:

| file | §8 C1 record | live runtime (`/opt/workbench/app/…`, the bind-mounted source) |
|---|---|---|
| `strategies_user/templates/sector_rotation.py` | `5eaba72c…` 22421 B | **`6ee3953d…` 21990 B** |
| `app/factor_data/factors/sector.py` | `7e7f6cc4…` 7165 B | **`7d91e159…` 7014 B** |

The §8 bytes do exist on the box — at **`/opt/workbench/staging/`** (mtime 2026-08-12), a staging
working copy, **not** the live bind mount. The live bytes are byte-identical to the tracked copies at the box's deployed
commit **`0344337`** (verified by SHA-256 against `git show 0344337:<path>`, not by inspection).
`0344337` is an ancestor of `origin/main` @ `4c4a2b10`, 5 commits behind, and **neither of these two
files changed across those 5 commits** — so the runtime blobs equal `origin/main`'s copies as well.
The box tree as a whole, however, is at `0344337`, not at main.

**Resolved — the content is identical; only the line endings differ.** The size deltas are exactly
the line counts:

```
sector_rotation.py   21990 B + 431 lines = 22421 B   (= the §8 C1 figure)
factors/sector.py     7014 B + 151 lines =  7165 B   (= the §8 C1 figure)
```

⇒ `/opt/workbench/staging/` holds **CRLF renderings of the same logical files** that are deployed
with LF. No commit in any branch produces `5eaba72c…`; the only tracked blobs for that path are
`3b29432e` / `6ee3953d` / `fb13112d`. This is the known
*governance-hashes-from-a-Windows-worktree* trap: **§8's C1 identity was hashed from a CRLF copy,**
not from the runtime.

**Therefore the deployed SEC-001 code did NOT change between C1 and today** — the apparent drift was
an encoding artifact, not a redeploy of this strategy. The box *was* separately redeployed 2026-08-23
(image `fc76c0ed7015` built 08-23 16:16 EDT, container created `2026-08-23T20:17:44Z`, rollback tag
`trading-workbench-backend:rollback-pre-prs-20260823`), but that deploy left both of these files
byte-unchanged in content.

⇒ **Corrective actions:** §8's identity block must be read as *content-identical, CRLF-encoded* — it
must not be quoted as a runtime hash. C6's post-containment snapshot must record the **LF** runtime
identity above, and any future identity check on this box must hash the **container** path
(`docker exec … sha256sum /app/…`) or a Git blob, never a `staging/` working copy.

⚠ **The finding itself is unaffected.** Both defects are present in the *currently deployed* bytes,
confirmed in `origin/main`'s copy of the file that hashes to the runtime blob:

- line 58 — `"sector_momentum_skip_days": 0,  # no skip (matching Momentum)`
- line 289 — `per_name = min(equity / Decimal(k), …)` with `k = len(target)`, i.e. per **name**
- line 228 — docstring still claims `(1/K)·(1/n_sector)`, which line 289 does not implement

⇒ G3 and G4 are genuinely open against `origin/main`, not stale.

### 13.3 BLOCKER — C5b has a second blocker beyond credentials

`scripts/flatten_account.py` **does not exist on the box** — not in the container's `/app/scripts`
(which is otherwise fully populated), not on the host tree, not anywhere under `/opt/workbench`.

Cause: the file is **not on `origin/main`**. It is committed only on the local working branch
`research/mr002-validation2-lineage` (`apps/backend/scripts/flatten_account.py`, sha256
`9d40238adaa4d9017936a2ea96c9664800bb291a81aaed8c14802e84a47c2877`). The box deploys main, so it
never received the tool.

⇒ **C5b cannot execute today until the script is placed on the box.** Its dependencies (`httpx`,
`pyotp`) are already importable in `workbench-backend`, so the minimal path is a `docker cp` into
the running container — `/app/scripts` is **not** a bind mount, so the copy is confined to the
container's writable layer and disappears on recreate, which is the correct lifetime for a one-shot
tool. ⛔ Do **not** redeploy the box to deliver it: a redeploy changes runtime identity mid-incident
and starves the MDQ capture disk.

### 13.4 C5b pre-flight risk record (measured, so the run is not a surprise)

| Factor | Measured | Verdict |
|---|---|---|
| Breaker latched? | `accounts.circuit_breaker_tripped_at` = **NULL** for all 7 accounts | ✅ clear |
| `max_orders_per_minute` (user 5, limits id=7) | **200** vs 99 sells | ✅ no pacing needed |
| `max_orders_per_day` (user 5) | **NULL** = unlimited; 0 orders today | ✅ |
| Daily-loss breaker headroom | `equity 100,179.99 − last_equity 101,342.08 = −1,162.09`; cap 5,000 ⇒ **≈ $3,838 headroom** (~3.8% of book) | ⚠ see below |
| `/api/v1/positions` pagination | none — returns all rows for `user_id`; 99 positions, all on account 5 | ✅ no silent truncation |
| Position granularity | **fractional** (`MSTR 10.93976`, `CRM 5.443727`) | ⚠ fractional market sells are RTH-only |
| Long/short | 99 long, `allow_short=0`; every sell is position-reducing | ✅ passes the short gate |

⚠ **The daily-loss gate does not exempt sells.** `RiskEngine` step 9 and
`CircuitBreakerService.check()` both measure `equity − last_equity` (`day_change_basis =
BROKER_LAST_EQUITY`) and gate *every* order, sells included. Flattening does not itself move that
number — a market sell swaps stock for cash at the same mark — so only adverse market drift can trip
it. But if drift consumes the $3,838 mid-run, the breaker **latches** and every remaining sell is
rejected `CIRCUIT_BREAKER`, leaving account 5 **partially flattened** — a residual unmanaged book,
arguably a worse state than either endpoint.

⇒ **Mitigation:** `flatten_account.py` is idempotent (it re-reads positions each run and sells
exactly what is held), so the recovery is: reset the breaker in Settings → Risk, then re-run. Run
`--dry-run` first to confirm the 99-name list before submitting.

⚠ Also note `last_equity` is Alpaca's field, not a verified prior close — the −1,162.09 baseline
inherits that known unreliability, so treat the headroom figure as approximate.

### 13.5 Custody gap — this document is untracked

This incident record is **`??` untracked in Git**. `.gitignore` lines 107–108 explicitly un-ignore
`/docs/incidents/**`, so this is an oversight, not policy: the file was never `git add`ed. Its only
copy is the operator laptop working tree on branch `research/mr002-validation2-lineage`.

⇒ The sole record of a live containment action has no custody and no second copy. It should be
committed before C5b changes the state it describes — the C1/C6 pair is meaningless if the document
binding them can be lost.

### 13.6 Status entering RTH 2026-08-24

- Containment: ✅ **verified holding**; the 10:24 ET slot cannot fire.
- C5b: ⛔ blocked on **(a)** user-5 credentials (no compliant agent transport) **and** **(b)** the
  missing script on the box (§13.3). Book carries **99 positions / $97,854.74** into the session.
- C6: ⬜ pending C5b.
- G3–G6: ⬜ open, and gated behind C6 per §8.

---

## 14. C5b + C6 — EXECUTED AND CLOSED, 2026-08-24

### 14.1 C5b — flatten

Executed during RTH on 2026-08-24. Submission path was the authenticated HTTP API
(`flatten_account.py` → `POST /api/v1/orders` → OrderRouter → risk engine → audit), per ADR 0002.
**No direct broker liquidation and no DB edit was used at any point.**

Transport note: the tool was delivered by `docker cp` into `workbench-backend` (see §13.3) and driven
over an **SSM port-forward of :8000**, so the credential never entered an SSM command body, an
instance command history, or `/var/lib/amazon/ssm/.../_script.sh`.

| | |
|---|---|
| Dry run | 99 positions resolved, login OK, **0 orders submitted** |
| Live submit | **99 SELL orders, 0 rejected** — every order returned a `broker_order_id` |
| Rejections | none: no `CIRCUIT_BREAKER`, no `RATE_LIMIT`, no `MARKET_SESSION_CLOSED` |
| Breaker headroom at submit | `day_change −1,886.63` vs cap 5,000 ⇒ **$3,113 headroom**, breaker `NULL`, `trading_blocked=0` |
| Settlement | 13:41:35Z — **99 FILLED / 99 fill rows / 0 positions / 0 non-terminal** |

⭐ **Fill-ingest lag reappeared and self-resolved.** Immediately post-submit the platform showed
`SUBMITTED 99 / fills 0` while positions were already **0** — positions sync by REST poll, order
lifecycle by the trade-updates stream. Consistent with the recorded EC2 behaviour (latency, not loss;
prior measurement 8 m 31 s). It settled in **~3 minutes** with no manual reconciliation.
⛔ Per **INV-EXEC-01**, the absence of a platform fill record was *not* treated as "unfilled" — the
run polled to settlement rather than retrying. Had it been read as unfilled, a retry would have
double-sold.

### 14.2 C6 — post-containment verification: **PASS**

`scripts/c6_verify.py`, read-only (`mode=ro`), fail-closed. ⭐ It was **run before the flatten and
returned FAIL (exit 2)** on `positions == 0` and `flatten audit trail present` — so the PASS below is
a state change, not a vacuous green.

| Criterion | Result |
|---|---|
| `positions == 0` | ✅ 0 remaining |
| `non_terminal_orders == 0` | ✅ 0 open |
| strategy 7 still `IDLE` | ✅ IDLE |
| no scheduled/runnable dispatch | ✅ `runnable=False` (IDLE ∉ `ENGINE_RUNNABLE_STATUSES`) |
| account cash/equity captured | ✅ equity **99,262.44**, cash **99,262.44** (fully in cash) |
| flatten audit trail present | ✅ 99 sells; 298 user-5 audit rows today (`ORDER_RISK_PASSED` 99 + `ORDER_SUBMITTED` 99 + fill ingests) |
| runtime identity recorded (LF) | ✅ `sector_rotation.py` `6ee3953d…` (21990 B), `factors/sector.py` `7d91e159…` (7014 B), `crlf_present: false` |

### 14.3 Custody — C1/C6 pair complete

```
object   : s3://workbench-evidence-incidents-219024422756/
           sec001/2026-08-24/sec001_post_containment_c6_20260824T134150Z.json
VersionId: 3snS8HgJzNUHF24BwAIiUfCSHn9lLikb
sha256   : 132fae12406fae88207a8cf39805222e2cebe95bd2188873ac1146153dc20adf
bytes    : 135589
lock     : COMPLIANCE, retain-until 2033-08-22T13:42:20Z
```

S3 server checksum decodes to the local sha256 **exactly**. ⭐ `HeadObject` from the host returns
**403** — expected, and a positive control: the instance role is **write-only** by bucket policy
(§8.1). Retention was confirmed with admin credentials instead.
⭐ Per §13.2 the identity recorded here is the **LF** runtime blob, not §8's CRLF artifact.
⭐ No write probe was placed inside the evidence prefix this time (§8.1 records why that matters).

### 14.4 Gate status after C6

| Gate | State |
|---|---|
| G1 evidence quarantine | ✅ |
| G2 blast radius | ✅ CLOSED |
| **C5b / C6** | ✅ **CLOSED — account 5 flat, $99,262.44 all cash, containment sealed** |
| G3 mechanical conformance repair | ⬜ open — now unblocked (§8 gated §9/§10 behind C6) |
| G4 representability fail-closed | ⬜ open |
| G5 SEC-001 V3 research | ⬜ open |
| G6 fresh paper accrual | ⬜ open — starts from zero after an approved V3 activation |

Account 5 becomes eligible for a later V3 reset only from this sealed clean state. The prior eight
weeks remain non-conforming and carry zero promotion credit (G1).
