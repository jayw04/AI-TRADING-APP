# Strategy 9 / Account 7 — activation authority reconciliation (2026-08-31)

> # ⛔ SUPERSEDED CONCLUSION — READ FIRST
>
> **§8.2's conclusion *"there was no unauthorized account remap"* is WITHDRAWN.**
>
> Account 7 did **not** merely continue under an unchanged binding. Evidence now establishes a
> **2026-07-07 rebinding whose authorization is not reconstructable** from the currently identified
> system of record (ADR 0052, §11 WP1.6). My independent order trace corroborates it: account-7
> activity begins 2026-07-07 ×188, ADR 0052 names a 2026-07-07 rebinding, and its 08-14 "83 == 83"
> state reconciles to today's 51 via the 08-20 batch of 32.
>
> ⛔⛔ **Hold the epistemic boundary exactly here: "authorization NOT DISCOVERABLE", never
> "UNAUTHORIZED."** Absence of discoverable authorization is not proof of unauthorized action.
>
> ```
> ACCOUNT-7-BINDING-PROVENANCE = REBINDING OBSERVED / AUTHORIZATION NOT DISCOVERABLE
>                              / AUDIT INCOMPLETE
>                              / DO NOT CLASSIFY AS AUTHORIZED OR UNAUTHORIZED YET
> ```

⛔ **Read-only reconciliation.** Strategy 9, Account 7, and its 51-position book were **not touched**.
No activation, rebalance, or mutation. This record establishes *what the custody says*; it authorizes
nothing.

---

## Verdict

```
STRATEGY-9-ACTIVATION-AUTHORITY = LOCATED / NO EXECUTION AUTHORIZATION HAS EVER EXISTED
                                / READINESS AUTHORIZATION LAPSED UNEXERCISED 2026-08-18
                                / ACTIVATION PROHIBITED
```

⚠ **This is NOT "FROZEN / NO-GO."** Neither phrase appears in the custodied governance surface. The
custodied position is different and stronger in one respect: activation was never authorized in the
first place, so there is no ruling to lift — there is an authorization that does not exist.

---

## 1. The governing surface — located

**`docs/design/WSS_ACCOUNT7_READINESS_AND_SEQUENCING_001.md`** (12,978 B, `origin/main`)
Document ID `WSS-ACCOUNT7-READINESS-AND-SEQUENCING-001`, dated 2026-08-03.

> Status: **Active working plan — supersedes no governed authorization**
> Scope: **Sequencing and blocker state only. Authorizes nothing.**

It names its own upstream authority: **`docs/design/ADR0043_LIVE_CANARY_WS5_SUCCESSOR_START_001.md`**
("governing authorization", §9).

## 2. The dispositive clause — §4, scope boundary

The successor authorization **ends at READY**. Its own stage table:

| stage | under this authorization? |
|---|---|
| A adopt and verify clean resources · B inert runtime · C read-only reconciliation → `READY` · D readiness record | ✅ yes |
| **Bind WSS config to account 7** | ❌ **no** |
| **Fresh target + activation manifest** | ❌ **no** |
| **Canary activation / any order** | ❌ **no** |
| **Scheduler activation** | ❌ **no** |

> *"Completing this authorization produces a verified-ready, flat, inert account — **not a trading
> one**. Everything from binding onward requires a **separate authorization, which does not yet
> exist**."*

It also pins `broker_access_mode = read_only`, `strategy_execution_enabled = false`,
`scheduler_enabled = false`, `alpaca_startup_enabled = false`.

## 3. And that readiness authorization has since LAPSED

**`docs/design/ADR-0043/ADR0043_WS5_TERMINAL_DISPOSITION_20260829.md`** §8 (2026-08-29):

> *"Authorization **lapsed unexercised (2026-08-18)**; compute retired; evidence custody now wholly
> in versioned S3…"*

Consistent with §3 of the readiness plan: *"Effectiveness trigger PR is open and green, **not
merged**. No clock has started. Stage A held."*

⇒ Not only does no execution authorization exist — the **readiness** authorization that would have
produced a verified-ready inert account expired without being exercised.

---

## 4. Surviving blockers, classified

| # | requirement (source) | class |
|---|---|---|
| §5.1 | Factor-data refresh — *"the true critical path"* | **SATISFIED** 2026-08-31 (factor GREEN) |
| §5.2 | Forced-expiry / partial-fill negative-path evidence — *"a stated precondition for transition"* | **OPEN** — parked on account 3 (not activated, breaker tripped). *"Leaving it parked is not [acceptable] — it silently blocks transition."* |
| §8.1 | Effectiveness-trigger merge (starts the 336-hour clock) | **OWNER DECISION** — overtaken: the authorization lapsed |
| §8.2 | Factor-refresh fix — scope and timing | **SATISFIED** — delivered and accepted 2026-08-31 |
| §8.3 | Account 3 — unblock, or re-scope the forced-expiry evidence | **OWNER DECISION** |
| §8.4 | **Execution authorization beyond Stage D — who drafts, and when** | **OPEN / OWNER DECISION** — this is the missing activation authority |
| §7 | WSS dispatch disabled while factor readiness non-green | **SATISFIED** — ⚠ but §7 says plainly *"The factor issue does not by itself block account binding"* |

⭐ §7 is independent confirmation of the platform-level point: **factor GREEN was never the thing
gating Account 7.** It removed one constraint that was never the binding one.

---

## 5. ⚠ Two discrepancies — NOW RESOLVED, see §8

**5.1 — Broker identity disagreement (three account numbers in play).**
The custodied surface **hard-pins** account 7 = **`PA3E97RWHKQZ`** (cred key fp `ffab8796516a`,
secret fp `c2cab6509f1b`) and warns: *"⚠ Do not repoint account 7 to `PA34USW0Q8UO`. That is the
legacy canary's account."* Working notes instead record acct-7 identity as **`PA3BGKRLH2AP`**, key
rotated 2026-08-18 → fp `b56421a28128`.
⛔ **Unresolved.** No future activation classification may be made until the live broker identity is
verified against the custodied pin.

**5.2 — The account is not flat, and the custody says it should be.**
§4 states completing the authorization yields a *"flat, inert account"*; §1 says *"The dedicated
account is clean, so the old 47-fill residual plan is void. Exits should be empty — the gate must
*verify* that, not assume it."* **Account 7 holds 51 nonzero positions** (observed 2026-08-31).
Either the DB's account 7 does not point at `PA3E97RWHKQZ`, or the book was established outside this
surface.
⛔ **Unresolved and material.** ⛔ Do not reconcile it by mutating anything.

## 6. Custody gap — the transition protocol (⚠ CORRECTED, see §8.3)

`docs/adr/` runs `…0049, 0051, 0055, 0056` — **0052, 0053 and 0054 are absent**. The
"Transition Protocol v2.1 / ADR 0054" referenced in working notes is **not in Git custody**.

**`STRATEGY-9-TRANSITION-PROTOCOL-CUSTODY-001` — AUTHORITY NOT LOCATED IN GIT.** Same class as the
S8.6 custody question: a confidently-cited protocol whose custodied source does not exist. ⛔ Do not
treat the transition protocol as governing until it is located.

---

## 7. What this changes, and what it does not

**Changes:** strategy 9 is no longer classified from working notes. Its disposition is now
evidence-grounded, and the earlier working-note labels "FROZEN / NO-GO" are **not** what the custody
says.

**Does not change:** strategy 9 stays `IDLE`. ⛔ No activation, no binding, no rebalance, no
liquidation, no touch of the 51-position book. The two discrepancies in §5 and the custody gap in §6
must be resolved before *any* future activation classification — and none of that is engineering
work; it is evidence reconciliation and owner decisions.

---

# 8. PRE-AUTHORIZATION RECONCILIATIONS — executed read-only 2026-08-31 16:50Z

⛔ Nothing was activated, bound, rebalanced, liquidated, remapped, or credential-changed. The only
broker call was `GET /v2/account` — a **permitted read** under the surface's own
`permitted_endpoints`.

## 8.1 Broker identity — RESOLVED, and the CUSTODIED PIN IS NOT THE LIVE ACCOUNT

| source | account number | verdict |
|---|---|---|
| **live** `broker_registry.get(7).get_account()` | **`PA3BGKRLH2AP`** | — |
| custodied pin, `WSS_ACCOUNT7…001` §1 | `PA3E97RWHKQZ` | ❌ **MISMATCH** |
| legacy canary (§1 warns against) | `PA34USW0Q8UO` | not it |
| working notes | `PA3BGKRLH2AP` | ✅ **MATCH** |

⭐⭐⭐ **The working notes were right and the custodied surface is stale on identity.** ⛔ This
inverts the usual precedence and must not be forgotten: *custody is authoritative about **decisions**,
but it can still be **stale about facts**.* Verify a pinned identity against the live system before
relying on it.

## 8.2 The 51-position book — provenance ESTABLISHED

407 orders on user 7, **406 FILLED / 1 REJECTED**, `source_type` **405 STRATEGY / 2 MANUAL**:

| date | orders |
|---|---|
| 2026-07-07 | 188 |
| 2026-07-13 | 98 |
| 2026-07-20 | 86 |
| 2026-07-29 | 2 |
| 2026-08-13 | 1 |
| **2026-08-20** | **32** |

**Nothing since 2026-08-20 17:07.** Strategy 9 has 91 `strategy_runs`; the last ended
**2026-07-28 14:45** (`IDLE`). ⚠ Do not read "open run" from `ended_at IS NULL` — that field is a
known-unreliable indicator here.

### ⇒ The §5.2 contradiction dissolves — there was no unauthorized remap

The book was built on **`PA3BGKRLH2AP`** starting **2026-07-07**, *before* the 2026-08-03 readiness
plan was written. That plan describes a **planned successor account** (`PA3E97RWHKQZ`) which was
**never adopted** — its authorization **lapsed unexercised 2026-08-18**.

⇒ Most consistent reading: **the custodied surface governs a successor account that was never taken
up, while live account 7 continued on the pre-existing `PA3BGKRLH2AP` book.** The surface is not
describing the live account at all. ⚠ This is an inference from identity + timing, not an owner
ruling; it would be **refuted** by evidence of a governed remap after 2026-08-03.

## 8.3 🐛 CORRECTION — ADR 0054 EXISTS and is ACCEPTED; it is merely NOT ON `main`

My §6 finding *"the transition protocol has no ADR / authority not located in Git"* was **WRONG**.

| ADR | on disk | on `origin/main` | elsewhere |
|---|---|---|---|
| **0054** transition-residual-risk-continuation-policy (24,902 B) | ✅ | ❌ | ✅ commit `85e45984`, branch `governance/adr0054-transition-residual-risk` (2026-08-21) |
| **0053** strategy-performance-epochs (20,652 B) | ✅ | ❌ | — |
| **0052** broker-binding-change-auditability (10,242 B, **Draft**) | ✅ | ❌ | — |

ADR 0054 header: *"**Status: Accepted** (owner rulings 2026-08-21) · amended the same day — v2.1"*.

⭐⭐ **Restated finding — `STRATEGY-9-TRANSITION-PROTOCOL-CUSTODY-001` = ACCEPTED BUT NOT MERGED TO
`main`.** That is a *different and arguably worse* state than "does not exist": a policy marked
**Accepted** and cited as governing, sitting on an unmerged branch where `main`'s custody cannot see
it. ⛔ Do not treat it as governing from `main`; ⛔ equally, do not now claim it does not exist.

⭐⭐ **And note what ADR 0052 is about: "Auditable broker-binding changes" (Draft, 2026-08-14).** The
one ADR that would make a broker-binding change auditable is an **unmerged draft** — while account 7's
binding is precisely what §8.1 shows diverging from custody. That is the gap that let §8.1 happen
silently.

---

# 9. Standing after these reconciliations

**Strategy 9 / Account 7 = `IDLE` / `ACTIVATION PROHIBITED` / authority gap resolved as "no authority
exists".** ⛔ Unchanged by §8 — none of these findings creates activation authority, and no execution
authorization should be drafted preemptively.

Open for owner decision: whether ADR 0052/0053/0054 should be brought onto `main`; whether the
custodied identity pin should be corrected or the surface retired; and §8.4's original question —
whether a new execution authorization should be designed at all.

---

# 10. ADR 0054 REVIEW — is the "Accepted" ruling valid and current?

Read-only, 2026-08-31. Five questions, five answers.

## Q1 — Was `85e45984` owner-approved as the final ADR 0054? **ASSERTED, NOT VERIFIABLE**

The ADR states *"Status: Accepted (owner rulings 2026-08-21) · amended the same day — v2.1"* and
carries a detailed §10 amendment log (v2.0 → v2.1 → **v2.1 hardened**, all 2026-08-21, the last
described as an *"Owner review pass"*).

⛔ But **there is no PR, no review trail, and no push.** The approval exists *only as
self-assertion inside the artifact* — exactly the failure mode established earlier today: **never
read custody or approval status from inside the document.**

## Q2 — Is the byte identity still what was approved? **BYTE-STABLE; CORRESPONDENCE UNPROVEN**

`24,902 B`, sha256 **`77c86df9a8c41705…`**, byte-identical at `85e45984` and on disk, pure LF
(raw == CR-stripped). Branch head **is** `85e45984`, exactly **1 commit** ahead of `origin/main`.

⇒ Stability is proven. **Correspondence to what was approved is not** — no independent record of the
approved bytes exists to compare against.

## Q3 — Why was it never merged? **IT WAS NEVER SUBMITTED**

Branch `governance/adr0054-transition-residual-risk` is **local-only — not on `origin`** — and
**no PR has ever existed**.

🚨 **It has never left this laptop.** ADR 0054 *and the entire v13 executable stack* are a single
point of failure. Same pattern as the ADR-0043 corrections living only in a local worktree.

## Q4 — Has later governance superseded any provisions? **A REAL INTERACTION — MUST BE ADJUDICATED**

**ADR 0055** — *"Position-notional cap requires a trusted reference price"*, **Accepted 2026-08-25,
on `main`** — **references ADR 0054** and postdates it by four days.

ADR 0054 §8 retires the *"every individual gate must PASS"* owner override, justifying it with a
*"single ~$65 stale-reference failure"* (ALAB, 2026-08-20, manifest `30a53127…`). ADR 0055 addresses
**exactly that class** — an untrusted reference price in the `max_position_notional` gate.

⇒ ADR 0055 may have repaired the **root cause** that ADR 0054 §8 used as its justification.
⛔ Not asserting supersession — flagging that this specific interaction **must be adjudicated before
ADR 0054 is relied upon**.

## Q5 — Merely custody a made decision, or create new authority? **DECISIVELY MORE THAN CUSTODY**

**(a) `85e45984` is NOT docs-only.** 19 files, **6,943 insertions**:

| | lines |
|---|---|
| `ops/acct7/v13/v13_transition_executor_v10.py` | 1,061 |
| `ops/acct7/v13/v13_transition_planner_v8.py` | 924 |
| `ops/acct7/v13/v13_execution_core_v3.py` | 705 |
| `v13_continuation_policy.py` · `v13_residual_debt.py` | 243 · 269 |
| `v13_frozen_execution_limits_v8.json` · 3 seal JSONs · `CUSTODY.json` | 423 + 245 + 127 |
| 6 test files | ~2,059 |
| `.gitattributes` | 10 |
| ADR 0054 + design proposal | 877 |

⇒ Merging lands **~4,000 lines of executable, order-submitting transition machinery**.

**(b) ADR 0054 §8 retires a standing owner override.** *"The 'every individual gate must PASS' owner
override is retired"*, replaced by a more permissive scheme. That is a **live relaxation of a gate**,
not a record of a past decision.

🚨 **Merging `85e45984` would be a substantive code + policy change, not a documentation custody
action, and must not be processed as one.**

## Incidental findings

- ⭐ **The "Account 7 remains frozen" language traces to ADR 0054's closing paragraph** —
  *"51-position reconciled book, strategy 9 IDLE v1.4.0, gross cap $100,000, no reload, no `/start`,
  no C40 epoch, no manual sale of residual names, zero orders."* So the FROZEN characterisation is
  real, but it lives **off-`main`**. §1's earlier conclusion stands for `main`'s custody.
- ⭐ ADR 0054 also states *"**No live execution was performed under Protocol v2 or v2.1**"* and
  contemplates *"the next live attempt … in a new trading session"*. It is an **active continuation
  policy, not a retirement document** — relevant to the restore-vs-retire decision.
- 🐛 Doc defect: **section number 9 is duplicated** — *"### 9. The manifest discloses the rule"*
  (under Decision) and *"## 9. Activation invariants"* (top-level).
- ⚠ **ADR 0056 on `main` reads "Status: Proposed — becomes Accepted on owner approval of this PR."**
  It governs the factor-readiness activation interlock that was proven and accepted today; that
  status line may now be stale. Flagged, not changed.

---

# 11. STRATEGY-9 RESTORE — WP1 RESULTS (preservation + policy reconciliation, read-only)

**Owner decision recorded:** `STRATEGY-9-DISPOSITION = RESTORE / COMBINED-BOOK THESIS RETAINED /
RESOLVE BLOCKERS PROSPECTIVELY / NO EXECUTION AUTHORITY YET` — owner ruling, 2026-08-31.
⚠ **Rationale not stated in-session.** No economic or strategic assessment of the combined-book
thesis was produced by this session, and none was supplied to it. This is recorded as an owner
decision, **not** as a conclusion derived from evidence gathered here.

## WP1.1–1.2 — Preservation: DONE, and it is NOT on `main`

Pushed the exact commit to a quarantine ref. **No PR opened. Not merged. Not on `main`.**

```
ref          refs/heads/quarantine/adr0054-v13-CUSTODY-ONLY-do-not-merge
commit sha1  85e459840971e9638e116906fd4366a9ae4d09e0
tree   sha1  edef89610755b88eeecf13bf2247706dd43748e7
ADR0054 blob 30be90cd19a10299d2e36192554b5c4029021754  (24,902 B · content sha256 77c86df9a8c41705…)
scope        19 files / 6,943 insertions
```

**`85e45984 = CUSTODY ONLY / UNREVIEWED FOR CURRENT AUTHORITY / MUST NOT MERGE OR EXECUTE / NO
ACTIVATION AUTHORITY`**

⭐ Verification note: **remote and local tree sha1 are identical**, which proves every one of the 19
blobs is byte-identical — a git tree hash covers each entry's mode, name and blob hash recursively.
A per-file loop is redundant (and quadratic; mine timed out before I recognised that).

## WP1.3 — ADR 0054 §8 vs ADR 0055: **NO** — they govern DIFFERENT MECHANISMS

| | ADR 0054 §8 `stale_reference` | ADR 0055 |
|---|---|---|
| component | the **v13 transition executor's own** abort taxonomy | the **risk engine's** `_reference_price` for `max_position_notional` |
| rule | a **300-second staleness rule** — ADR 0054 states *"The 300-second stale-reference rule is not changed"* | resolution chain `limit_price → reference_price → cached close → None` |
| class | `EXECUTABILITY` → order refused, continuation decided on residual | pre-0055 behaviour was **fail-OPEN** — orders passed *trivially* |
| could it produce the ALAB abort? | **yes** — it refuses the order | **no** — a fail-open gate cannot abort |

⇒ **ADR 0055 does not eliminate or weaken the failure ADR 0054 §8 relied on.** The $65.07 ALAB abort
came from the executor's own staleness gate, not from the risk engine's cap. ⛔ Do not treat 0055 as
superseding 0054 §8.

### ⚠ But ADR 0055 creates a NEW interaction ADR 0054 could not have modelled

ADR 0055 makes a missing price **fail-CLOSED** for `max_position_notional` on exposure-increasing
orders. A risk-engine refusal maps to ADR 0054's taxonomy as **`risk_refusal` — a HARD code →
immediate `HALTED_REQUIRES_REVIEW`, never budget-eligible.**

⇒ Under ADR 0055, an unpriceable exposure-increasing order in a Strategy-9 transition now triggers an
**immediate HARD halt** where it previously passed trivially. That is a **new halt surface inside the
transition path**, introduced four days after ADR 0054 was written, which its continuation policy
never modelled. **This must feed the successor design.**

## WP1.5 — The all-gates-PASS override: NOT IN `main` CUSTODY, and it REMAINS CONTROLLING

The *"every individual gate must PASS"* owner override has **zero occurrences in any `main`-custodied
document**. It survives only in: ADR 0054 §8's description of retiring it; the quarantined
`v13_frozen_execution_limits_v8.json` key **`retired_owner_override`** (line 349); and working notes.
ADR 0054's *"Supersedes: the stage-continuation clauses of frozen execution limits v5"* — limits v5 is
likewise not on `main`.

⚠ **TIGHTENED (owner correction).** ⛔ Do **not** manufacture the positive proposition that an exact
textual *"all gates must PASS"* rule is currently custodied on `main`. It is not — zero occurrences.

The only safe statement is the **negative** one:

> **ADR 0054's attempted relaxation has no established authority. Therefore no relaxation may be
> taken from ADR 0054.**

If an **independently established** prior owner ruling requires every individual gate to PASS, it
continues to apply **because of that independent ruling** — never because it was reconstructed from
ADR 0054's retirement language. ⛔ If the *only* evidence for the old rule is ADR 0054 saying it was
retired, the actual owner ruling must be **located** before the old rule is encoded into successor
code.

🚨 **`v13_frozen_execution_limits_v8.json` OPERATIONALIZES the retirement in code.** Executing the
quarantined stack would therefore *enact a gate relaxation that has no governing authority*. That
file is **RE-ADJUDICATE (blocking)** at minimum.

## WP1.4 — Quarantined stack inventory (first pass; **nothing modified**)

| component | class | why |
|---|---|---|
| `v13_frozen_execution_limits_v8.json` | **RE-ADJUDICATE (blocking)** | encodes `retired_owner_override`; enacts an unauthorized relaxation |
| ADR 0054 §8 gate relaxation | **RE-ADJUDICATE** | premise intact vs 0055, but authority self-asserted |
| `v13_transition_executor_v10.py`, `_planner_v8`, `_execution_core_v3` | **REVISE** | must model ADR 0055's new HARD `risk_refusal` halt surface |
| `v13_continuation_policy.py`, `v13_residual_debt.py` | **REVISE** | depend on the limits/taxonomy above |
| 6 test files (~2,059 lines) | **KEEP (as evidence)** | valuable conformance corpus; re-run against the *successor* policy, not to validate it |
| `.gitattributes`, seals, `CUSTODY.json` | **KEEP** | byte-custody protection for the seal artifacts |
| ADR 0054 §9 activation invariants | **KEEP / candidate** | fail-closed preconditions; independently sensible |

## WP1.6 — 🚨 ADR 0052 CONTRADICTS §8.2's "no unauthorized remap" conclusion

ADR 0052 (*Auditable broker-binding changes*, **Draft**, 2026-08-14, off-`main`) states directly:

> *"The historical finding is recorded as such: **the 2026-07-07 rebinding** cannot be completely
> reconstructed from the audit subsystem… **it asserts that no authorization is discoverable from the
> system of record**."*

And, describing account 7 at the time: *"as account 7's **83 == 83** does today"*.

⛔ **This materially corrects §8.2.** I concluded *"no evidence of an unauthorized account remap."*
ADR 0052 says something different and more precise: **a rebinding did occur on 2026-07-07, and no
authorization for it is discoverable.** That is not absence of evidence of a remap — it is a recorded
remap whose authorization cannot be found.

⭐ **Independent corroboration of R2's timeline:** my order trace found *surviving* account-7 order
rows beginning **2026-07-07 ×188** — the same date ADR 0052 names as the rebinding. ⚠ **Superseded
by §13.4:** surviving order rows begin 07-07, but append-only audit references establish
Account-7/user-7 order activity **by at least 2026-07-06**. ⛔ **The `orders` table is NOT a complete
historical ledger** — never restate "the book began on July 7". And **83 positions (08-14) − 32
orders (08-20) = 51 today**, which reconciles the position count exactly.

⚠ ADR 0052 is a **Draft, off-`main`** — evidence, not authority. But it is contemporaneous, and its
finding must be adjudicated before any Strategy-9 activation.

**Requirement promoted (not the artifact):** *future Strategy-9 activation must have an independently
auditable binding between internal Account 7, broker account identity, credential fingerprint,
strategy identity, and activation authorization.* ⛔ ADR 0052's Draft status is **not** promoted.

---

# 12. STRATEGY-9 RESTORE — revised gate structure (owner, 2026-08-31)

| gate | state | meaning |
|---|---|---|
| **R9-G1** strategy disposition | **PASS** | RESTORE; combined-book thesis retained (owner decision; rationale not stated in-session) |
| **R9-G2H** historical binding reconstruction | ✅ **CLOSED — AUTHORIZATION UNRECOVERABLE** | evidence exhausted; ⛔ never reopen as a historical-proof requirement |
| **R9-G2P** prospective auditable binding | 🚨 **OPEN / BLOCKING** | the real forward blocker (§14) |
| **R9-G3** current transition policy | **OPEN / BLOCKING** | ADR 0054 cannot govern; successor policy required |
| **R9-G4** executable implementation | **OPEN / BLOCKING** | quarantined v13 stack needs conformance review/repair |
| **R9-G5** account/book transition plan | **OPEN / BLOCKING** | 51-position starting book → governed target |
| **R9-G6** new execution authorization | **OPEN / FINAL** | owner authorization only after G2–G5 close |
| **R9-G7** controlled PAPER activation | **NOT REACHED** | execution only after G6 |

⚠ **R9-G2 was previously reported PASS. That is withdrawn** — see the banner at the top. The
*51-position book provenance* is substantially understood; what is open is the **authority of the
broker binding under which that book began**. Those are different questions.

⭐ **Factor readiness remains SATISFIED and is NOT promoted into a Strategy-9 authorization gate.**

## `ADR0054-v2.1 = NOT SAFE TO ADOPT AS-IS`

Independently of its custody/approval defect: a successor transition design **must** incorporate
ADR 0055's HARD-halt behaviour (an exposure-increasing order without a trusted reference price
becomes a `risk_refusal` → immediate `HALTED_REQUIRES_REVIEW`, not a budget-eligible residual).

## `v13_frozen_execution_limits_v8.json = RE-ADJUDICATE / ACTIVATION-BLOCKING`

It carries the unapproved relaxation into **executable configuration**, not merely into prose.
⛔ **The quarantined v13 stack must not be run — not even as a nominal "test activation" against
Account 7.**

---

# 13. WP2 — ACCOUNT-7 BINDING PROVENANCE RECONSTRUCTION (read-only)

```
ACCOUNT-7-BINDING-PROVENANCE = AUTHORIZATION UNRECOVERABLE
                             / AND THE EVENT ITSELF IS NOT DB-RECONSTRUCTABLE
                             / DO NOT CLASSIFY AS AUTHORIZED OR UNAUTHORIZED
```

## 13.1 🚨 The audit vocabulary makes a binding change STRUCTURALLY UNRECORDABLE

`audit_log` holds **26 distinct actions**, and **not one concerns credentials, broker binding, or
account identity**:

> `CIRCUIT_BREAKER_RESET/TRIPPED · MORNING_BRIEF_GENERATED · ORDER_* (10) ·
> RECONCILIATION_DISCREPANCY · RISK_LIMITS_UPDATED · SCANNER_RUN · STRATEGY_* (9) ·
> TRADING_PROFILE_UPDATED`

⇒ **A 2026-07-07 rebinding could not have produced an audit record, because no such action type
exists — and still does not.** The absence of a trail is **structurally guaranteed, not evidence of
concealment.** This is mechanical confirmation of ADR 0052's premise, and it is why ADR 0052 makes
the control *"a precondition for the next broker-binding mutation"* rather than a reconstruction
project.

## 13.2 What the DB *does* establish

| fact | evidence |
|---|---|
| account 7 row + user-7 Alpaca credentials created **together** | `accounts.created_at` and `user_credentials` both `2026-06-27 23:18:17` |
| `accounts.credentials_ref` for account 7 | **empty** — binding resolves via `user_credentials` **by `user_id`**, not via the account row |
| user-7 Alpaca key/secret **never updated on 07-07** | `updated_at = 2026-08-18 01:32:20` (the known 08-18 rotation) |
| a **bulk** credential update **did** occur `2026-07-07 16:06:21` | **users 1, 2, 3, 4 only** — within ~90 ms. **User 7 is NOT in that batch** |
| 07-07 strategy-9 lifecycle | `15:00:55 STRATEGY_UNREGISTERED` → `17:15:01 STRATEGY_UPDATED` + `STRATEGY_REGISTERED` → `17:24:10` first surviving order |

⇒ **There is no DB-observable credential or binding mutation for account 7 on 2026-07-07.** What is
observable is an unregister → update → re-register cycle of strategy 9.

## 13.3 Order sequencing — the question answered

The 188 surviving 07-07 orders ran **17:24:10 → 18:03:21**, i.e. **after** both the 16:06:21 bulk
credential event and the 17:15:01 strategy re-registration.

## 13.4 🐛 The orders table is TRUNCATED; the audit log is MORE complete

`orders` id range is **464–2065** (1,602 rows). Of user 7's **552** distinct numeric audit order
references, **145 have no surviving `orders` row** — including ids 203/204/205, which the audit
records as `ORDER_SUBMITTED` on **2026-07-06 15:20**, a day *before* the first surviving order.

⇒ **User-7 order activity began at least 2026-07-06, not 07-07.** My earlier "activity begins 07-07"
statement was true only of the *surviving* orders table. ⭐ The append-only hash-chained audit log
outlived an orders-table rebuild — **do not treat `orders` as the historical record.**

## 13.5 Terminal outcome, and why the search stops here

**`AUTHORIZATION UNRECOVERABLE`** — with a refinement: the *event* ADR 0052 names is itself not
reconstructable from `accounts`, `user_credentials`, or `audit_log` for user 7.

Remaining candidate mechanisms, none confirmable from the DB:
1. the `2026-07-07 16:06:21` bulk credential update — **but user 7 was not in it**;
2. an **`.env`-level `ALPACA_PAPER_N` remapping**, which by construction leaves **no DB trace at
   all** — consistent with the known off-by-one in that mapping;
3. evidence available to ADR 0052's author that this session has not examined.

⛔ **Hold the boundary: authorization NOT DISCOVERABLE, never UNAUTHORIZED.**

## 13.6 Consequence for the restore path

Per the owner's framing, `AUTHORIZATION UNRECOVERABLE` does **not** mean Account 7 can never trade
again. The clean route is to **establish today's binding prospectively under a new auditable binding
record and explicitly decline to retroactively bless 2026-07-07.**

That requires the ADR 0052 *requirement* (not its Draft): an independently auditable binding between
internal account, broker account identity, credential fingerprint, strategy identity, and activation
authorization — plus the **new audit action vocabulary** §13.1 shows is missing. ⛔ Until that exists,
**R9-G2 remains OPEN / BLOCKING.**

---

# 14. R9-G2 SPLIT — an impossible historical proof must not block Strategy 9 forever

```
R9-G2H  HISTORICAL BINDING PROVENANCE  = CLOSED / AUTHORIZATION UNRECOVERABLE
                                       / HISTORICAL EVENT NOT DB-RECONSTRUCTABLE
                                       / NO RETROACTIVE BLESSING
R9-G2P  PROSPECTIVE AUDITABLE BINDING  = OPEN / BLOCKING
```

⛔ **All further historical reconstruction of the July event STOPS.** The evidence has reached its
useful boundary. ⭐⭐ **The missing authorization trail is STRUCTURAL, not suspicious** — the audit
subsystem had no vocabulary for broker binding, credential identity, or account remap, so **absence
of an audit event can never be used as evidence that governance was bypassed.**

## R9-G2P closure criteria

1. Establish the intended present-day Account-7 ↔ broker-account binding.
2. Verify the live broker account independently.
3. Bind **internal account ID · broker account number · strategy ID · credential fingerprint ·
   execution authorization** into **one durable record**.
4. Add auditable **event vocabulary** for future binding / credential / account-identity changes
   (§13.1 proves all 26 existing actions lack it).
5. Ensure the **next mutation cannot occur without generating that audit record**.
6. Record explicitly: *"The 2026-07 binding authority is unrecoverable and is not retroactively
   ratified."*
7. ⛔ **Perform no actual rebinding** as part of the design/audit work unless separately authorized.

## ⛔ Non-negotiable design requirement

**The next activation authorization must reference the exact binding record by IMMUTABLE IDENTITY —
never merely "Account 7" or "the current Alpaca account".** That is precisely how the 2026-08-03
readiness plan's `PA3E97RWHKQZ` pin survived after reality had moved to `PA3BGKRLH2AP`. A name is not
an identity.

---

# 15. LANE P — authority archaeology: the pre-ADR0054 rule CANNOT BE LOCATED

**Result: NEGATIVE. `frozen execution limits v5` does not exist in git on any ref.** The only limits
artifact anywhere in the repository is `v13_frozen_execution_limits_v8.json`, and it exists solely
inside the quarantined commit.

The *"every individual gate must PASS"* rule is attested by exactly two artifacts, **both inside
`85e45984`, both authored in the same 2026-08-21 event**:

1. ADR 0054 §8 — describing the rule *in the act of retiring it*;
2. `v13_frozen_execution_limits_v8.json:349` — `"retired_owner_override": { "override": "every
   individual gate must PASS", "status": "RETIRED by owner ruling 2026-08-21", … }`.

⇒ **The old rule cannot be independently located, and neither can its retirement.** Both are
self-attested by the same unmerged package. Per the WP1.5 tightening, the only safe posture stands:

> **ADR 0054's attempted relaxation has no established authority; therefore no relaxation may be
> taken from ADR 0054.** ⛔ And the old rule must **not** be encoded into successor code merely
> because ADR 0054 says it existed.

## ⚠ A wider observation — a whole day of owner rulings lives only here

The same limits file attests several further **"OWNER RULING 2026-08-21"** items found nowhere else:
`target_reentry_rule` · `precedence_rule` (*"no rule is subordinate or disabled by another"*) ·
`historical_validity` (the 08-20 halt still halts under v2) · `activation_invariants`.
⇒ **An entire day's governance rulings are attested only inside an unmerged artifact.** That is the
finding, not any one rule.

---

# 16. LANE I — static conformance analysis of the quarantined v13 stack

⛔ Nothing modified. Nothing executed.

## 16.1 ✅ ADR 0002 is NOT violated — a near-miss false finding

The executor imports `AlpacaAdapter`, `StockLatestQuoteRequest`, `StockLatestTradeRequest` and
`GetOrdersRequest`, which *looks* like direct broker order submission. **It is not.** The actual
submission is:

```python
resp = self.api("/orders", "POST", body)     # v13_execution_core_v3.py:596
```

— the **platform's own `/orders` endpoint**, i.e. through `OrderRouter`. Confirmed by the code's own
comments: *"OrderRouter, so ADR 0002's single dispatch point is unchanged"* and *"POST /orders
(source=STRATEGY, strategy_id=9) → OrderRouter"*. The `alpaca.*` imports serve **market-data reads and
broker-state reconciliation** only.

⭐⭐ **Lesson: an import list is not a call graph.** I nearly recorded an ADR 0002 violation from the
imports alone; reading the submission path refuted it.

## 16.2 🚨 The ADR 0055 interaction, made concrete

```python
if resp.get("rejection_reason"):
    rec["abort_reason"] = "risk_refusal"; rec["failure_class"] = "HARD"; raise Halt(...)
```

A platform risk refusal ⇒ `risk_refusal` ⇒ **HARD** ⇒ **immediate halt of the entire transition**,
never budget-eligible. The taxonomy is correct — but ADR 0055 **changed how often it fires**.

**And here is the specific defect:** `v13_execution_core_v3.py:418` computes a trusted
`reference_price` (`plan = {"reference_price": ref, …}`) and applies a collar for limit orders — but
the `/orders` body is built with **`symbol, side, qty, type, tif, account_id, source,
client_order_id`, plus `limit_price` only when non-`None`**. For a `type="market"` plan
(`limit_price=None`, line 422) **the executor's own trusted reference price is never transmitted.**

⇒ Under ADR 0055 the gate's chain (`limit_price → reference_price → cached close → None`) falls
through to the **cached close**, and if that does not resolve, the order is **refused fail-closed** →
`risk_refusal` → **HARD halt on the first such order**.

**REVISE (specific, testable):** transmit the executor's already-computed `reference_price` in the
`/orders` body so ADR 0055's chain can use it, instead of degrading to the cached close.

## 16.3 Inventory refinement

| component | class | note |
|---|---|---|
| `v13_frozen_execution_limits_v8.json` | **RE-ADJUDICATE / ACTIVATION-BLOCKING** | carries `retired_owner_override` into executable configuration |
| `v13_execution_core_v3.py` | **REVISE** | must transmit `reference_price` (§16.2) |
| `v13_transition_executor_v10.py`, `_planner_v8` | **REVISE** | recalibrate for ADR 0055's raised HARD-halt frequency |
| `v13_continuation_policy.py`, `v13_residual_debt.py` | **REVISE** | depend on the limits/taxonomy |
| HARD/EXECUTABILITY taxonomy + declaration↔code identity check | **KEEP** | sound; the seal enforces limits-vs-code set equality |
| ADR 0054 §9 activation invariants | **KEEP (candidate)** | fail-closed preconditions |
| 6 test files (~2,059 lines), seals, `CUSTODY.json`, `.gitattributes` | **KEEP (evidence)** | re-run against the *successor* policy |
| ADR 0002 compliance | ✅ **KEEP — verified** | submission routes through `OrderRouter` |

---

# 17. RULINGS ON LANES P AND I (owner, 2026-08-31)

```
PRE-ADR0054-OWNER-RULE      = NOT INDEPENDENTLY RECOVERABLE
ADR0054 §8 RELAXATION       = NO GOVERNING AUTHORITY
2026-08-21-OWNER-RULINGS    = ASSERTED / INDEPENDENT AUTHORITY NOT RECOVERABLE
                            / RE-ADJUDICATION REQUIRED BEFORE EXECUTABLE USE
ADR0002 ORDER-ROUTING       = PASS  (no defect recorded)
```

⛔⛔ **Do NOT replace the missing rule with an inferred "every gate must PASS."** Both propositions
originate from the same unmerged 2026-08-21 package; **neither has independent authority.** The same
treatment applies to all four further rulings in `v13_frozen_execution_limits_v8.json`
(`target_reentry_rule`, `precedence_rule`, `historical_validity`, `activation_invariants`): they are
**useful candidate policy and evidence, not owner-approved governance.**

⭐ This is an opportunity, not a loss: rather than reconstructing contradictory historical authority,
**make explicit current owner rulings for the successor transition.**

---

# 18. `STRATEGY9-REFERENCE-PRICE-PROPAGATION-001` — IDENTIFIED / ACTIVATION-BLOCKING

**The invariant (stated first, deliberately):**

> The trusted price computed by the transition execution core must reach the ADR-0055 notional-risk
> decision **through the platform's supported request contract**, including for market orders.

## 🐛🐛 EARLIER PROPOSAL: **WITHDRAWN / INVALID** (not merely superseded)

I proposed *"transmit `reference_price` in the `/orders` body."* **That would have broken every
submission.**

- `OrderRequest` (internal risk type) has `reference_price` (`app/risk/types.py:39`) and
  `RiskEngine._reference_price` consumes it (`engine.py:698`).
- **But `reference_price` is absent from the entire `app/api/v1/schemas/` directory** — it is an
  **internal-only field with no HTTP channel**.
- `OrderCreateRequest` sets **`model_config = ConfigDict(extra="forbid")`**, documented as *"unknown
  fields are rejected so a typo can't silently bypass the risk engine via a misnamed override."*

⇒ Adding `reference_price` to the body yields a **422**, not a passthrough.

⛔ **Status: WITHDRAWN / INVALID.** It is not a superseded-but-plausible option; it does not work.
⭐⭐ **Two lessons, both load-bearing:** an **internal risk-model field is not automatically a valid
API field**, and **absence cannot be established from a partial schema read**.

## 🐛 A second self-correction — the v13 body IS conformant

I then claimed `source` and `strategy_id` were absent from the schema. **Wrong** — I had read only to
line 39; they are defined at **lines 43–44**. The v13 request body is fully conformant with
`OrderCreateRequest`. ⭐ Same trap as always: **a truncated read is not an absence proof.**

## Viable repair options (none chosen; WP3 decides)

| option | change | tier |
|---|---|---|
| **(a)** add `reference_price` to `OrderCreateRequest` + map to `OrderRequest` | API contract **and** order path | **Tier 3** |
| **(b)** executor submits **limit** orders so `limit_price` carries the trusted price — first in ADR 0055's chain, already in the contract, and the collar path already exists at `v13_execution_core_v3.py:427` | **no platform change** | executor-only |
| **(c)** ensure the cached-close path reliably resolves for the transition universe | data availability | — |

⛔ **(b) must NOT be selected merely because it is smaller.** WP3 compares the actual **semantics** of
all three across: execution quality · collar behaviour · partial-fill handling · stale-reference
behaviour · ADR-0055 risk behaviour · and **what happens when the price becomes unavailable between
planning and submission**. The mechanism stays genuinely open until that trace is done.

⭐ The correction improved WP3: the implementation choice is now **open** rather than accidentally
predetermined by my first (invalid) proposal.

---

# 19. ⛔ `85e45984` IS PERMANENTLY BYTE-FROZEN

**Do not "fix" its limits JSON or its reference-price path in place. It is not a development branch.**

It is now valuable **historical evidence**: it records exactly what the abandoned v13 transition
package proposed. Build the successor from a **current-`main` base**, selectively porting the KEEP
components plus reviewed repairs. Provenance chain:

```
historical candidate (85e45984, frozen)
   → explicit CURRENT owner policy (WP3)
      → successor implementation
         → tests
            → execution authorization
```

⭐ Far stronger than turning the quarantine branch into a development branch.

---

# 20. R9-G3 REFRAMED, and what WP3 must freeze

⛔ **R9-G3 is no longer "repair ADR 0054."** It is: *create a small current successor policy using
ADR 0054 / v13 as **evidence**, explicitly re-adjudicating only the rules actually required to
execute safely.*

**WP3 freezes six things** (design only — ⛔ not activation):

1. **Auditable binding contract** — internal Account 7 + broker identity + credential fingerprint +
   Strategy 9 + authorization identity, with mandatory audit events **before** future mutations.
2. **Transition safety taxonomy** — preserve the useful HARD/EXECUTABILITY distinction, but approve
   it **prospectively** rather than inherit authority from `85e45984`.
3. **ADR-0055 interaction** — trusted reference price must reach the risk engine for
   exposure-increasing orders; missing/untrusted price stays **fail-closed**.
4. **Continuation policy** — re-adjudicate residual budgets and HARD-halt semantics instead of
   inheriting the quarantined limits JSON.
5. **51-position starting state** — the **actual current book is the transition origin**. ⛔ Do not
   flatten merely to reproduce the abandoned clean-successor design.
6. **Activation invariants** — re-adjudicate the candidate §9 invariants explicitly. Their
   *implementation* may be KEEP-quality even though their *historical authority* is not established.

---

# 21. RULING SET AS AT 2026-08-31 CLOSE — carried into custody

```
ACCOUNT-7-BINDING-PROVENANCE   = AUTHORIZATION UNRECOVERABLE
PRE-ADR0054-OWNER-RULE         = NOT INDEPENDENTLY RECOVERABLE
2026-08-21-OWNER-RULINGS       = ASSERTED / RE-ADJUDICATION REQUIRED
ADR0054 §8 RELAXATION          = NO GOVERNING AUTHORITY
ADR0002 ORDER-ROUTING          = PASS
V13 HTTP ORDER BODY            = SCHEMA-CONFORMANT
STRATEGY9-REFERENCE-PRICE-
  PROPAGATION-001              = DEFECT/INTERACTION CONFIRMED
                               / REPAIR MECHANISM NOT YET CHOSEN
                               / EARLIER "ADD FIELD" PROPOSAL **WITHDRAWN / INVALID**
```

⭐ Every historical mistake above is **visibly superseded in place, never silently rewritten** — the
banner at the top of this record, §8.2, §13.4, §16.1 and §18 each retain the original claim alongside
its correction, so a future reader can see what was believed and why it changed.

## ⛔ `85e45984` REMAINS BYTE-FROZEN AND IS NOT THE WP3 WORKING BRANCH

Restated here deliberately, because it is the easiest mistake for a later session to make:

> **Do not "fix" the quarantine package.** Repairing its limits JSON or its price path in place would
> convert **historical evidence into a successor implementation** and destroy the provenance chain.
> WP3 branches from **current `main`** and selectively ports KEEP components plus reviewed repairs.

## WP3 path — the shortest credible route back to Strategy 9 PAPER trading

```
current owner policy → auditable Account-7 binding → successor transition semantics
   → selected price/risk mechanism → repaired implementation → tests
      → SEPARATE execution authorization
```

⛔ Without importing unverifiable 2026-08-21 authority at any step.
