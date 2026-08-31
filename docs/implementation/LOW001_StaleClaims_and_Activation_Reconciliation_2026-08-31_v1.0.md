# LOW-001 stale-claims inventory + activation reconciliation — 2026-08-31

⛔ **This is an INVENTORY, not a remediation plan.** No document is rewritten here, no strategy is
nominated or ranked, no state was changed. ⛔ **No runtime action is authorized by this
reconciliation.** Read-only throughout; superseded v0.2–v0.4 are left as historical evidence and are
**not** corrected to match today.

---

# A. Stale present-tense claims in the two live custodied surfaces

Only two custodied documents carry live status claims: **v0.5** (governing spec) and
**`…DynamicPIT_OPEN_TASKS_v1.0.md`**.

## A.1 — v0.5 header block (lines 5–8), the highest-traffic stale claims

| line | claim as written | today | class |
|---|---|---|---|
| 6 | *"Deployed runtime on ec2-paper: **v1.0.2** (`0344337`) — last known 2026-08-23; unverified since"* | box runs **`b94838b6…`** | **STALE** |
| 7 | *"DB `strategies.version` (strategy 8): **1.0.1** — behind both"* | DB says **1.0.3** | **STALE** |
| 8 | *"S8.6 failed once and must be rerun from check 1 on v1.0.3"* | full rerun ruled **NOT REQUIRED**; consumer (Track C) closed | **SUPERSEDED** |

## A.2 — v0.5 body

| line | claim | class |
|---|---|---|
| 92 | *"box runs 1.0.2, DB says 1.0.1, `main` is 1.0.3 — a three-way split"* | **STALE** — split resolved |
| 93, 184, 401 | *"all **39** Account-6 holdings"*; *"PAPER liquidation failed closed for all 39"*; *"current box state is unverified"* | **STALE** — 34 held, 34 resolve, 0 excluded (`S8.6-HOLDINGS-CARDINALITY-001`) |
| 386 | *"ec2-paper running image 1.0.2 (`0344337`) — not re-verified; SSH timed out"* | **STALE** |
| 387 | *"`strategies.version` row = **1.0.1** — never updated at the 1.0.2 cutover"* | **STALE** |
| 444, 446 | branch *"Already on v1.0.3/`956e932` → do not redeploy"* / *"Still on v1.0.2 → cutover"* | **STALE** — **neither branch applies** |
| 461 | *"deploy `956e932` using the governed full-cutover path"* | **STALE + PROHIBITED** — rollback to `956e932` is not authorized |
| 485 | check 2 pins `956e932` | **OPEN DEFECT** — `S8.6-CUSTODIED-CHECK2-UNSATISFIABLE-001` |
| 370 | *"1.0.4 Dynamic PIT acquisition — RESERVED, PR B"* | **HISTORICAL-ONLY** — Track C closed |
| §9 | *"S8.6 deployment proof — FAILED 2026-08-23 · rerun from check 1 pending — **the blocking gate**"* | **SUPERSEDED** — no surviving consumer |
| §9 | *"G4b operational reachability — FAILED on last-known v1.0.2 deployment; current box state unverified"* | **STALE** — now **PASS** (reachability) on `b94838b6…` |

## A.3 — `DynamicPIT_OPEN_TASKS_v1.0.md`

| line | claim | class |
|---|---|---|
| 50 | `DEPLOYED_BUILD_INFO.deployed_repository_commit = 0344337…` | **STALE** — now `b94838b6…` |
| 51 | *"`.deploy_src_sha` = `0344337…` — **agrees** with the build marker"* | **STALE** — the file is now **ABSENT** (`DEPLOY-SRC-SHA-LIFECYCLE-001`) |
| 52 | running template *"`version = "1.0.2"`"* | **STALE** |
| 53 | strategy 8 row *"`version=1.0.1` · `status=**PAPER**`"* | **DOUBLY STALE** — now `1.0.3` and **`IDLE`** |
| 73 | *"The v1.0.2 defect is live and reproducible today"* | **STALE** — repaired; identity resolves on frontier `2026-08-28`, 34/34 |
| 121–124 | A3 steps: deploy `956e932` · **update `.deploy_src_sha` by hand** · update version `1.0.1 → 1.0.3` | **STALE**; the hand-marker step now **contradicts** `DEPLOY-SRC-SHA-LIFECYCLE-001` |
| 128 | *"rerun S8.6 from check 1 — all twelve checks"* | **SUPERSEDED** |

## A.4 — ⚠ Unresolved evidence, NOT stale claims

- **Line 128's `AAPL → 199059` target for checks 3/8.** Today's boot log reports
  `security_identity_ready as_of=2026-08-28 permaticker=196290 probe=A`. The probe symbol was **not
  confirmed to be AAPL**, so `196290 ≠ 199059` is **not** evidence of drift. ⛔ Do not record this as
  stale without first resolving what `probe=A` is.
- **How `strategies.version` reached `1.0.3`.** A3 step 124 specified a governed one-row update while
  IDLE. The DB now reads `1.0.3`, but **this session did not establish which governed action produced
  it**. Classify as **unresolved evidence**.

---

# B. Strategy 7 — custodied activation surface LOCATED and read

**`docs/incidents/2026-08-22-sec001-production-conformance-failure.md`** (30,793 B, on `origin/main`).

> **Status: OPEN — containment authorized, execution blocked on credentials (see §8).**

- **Account 5 has never run frozen SEC-001.** The promotion shipped a different signal *and* a
  different construction; roughly eight weeks of "SEC-001" evidence describes a different book.
- *"Any future SEC-001 promotion evidence starts from zero, after an **approved V3 activation
  (G1, G6)**."* — no such approval exists.
- **§6 — the frozen construction is not deployable**, *"mathematical, not implementational"*.
- Strategy 7 was stopped **2026-08-22 15:46:06 UTC**, independently verified `IDLE`, scheduler job
  removed, run 765 closed.

⚠ **Stale claim found elsewhere:** the working note *"Live: SEC-001 sector-rot id=7 acct5"* is
**STALE** — strategy 7 has been IDLE since 2026-08-22.

⭐ Account 5 held **99 positions ($99,046)** awaiting a governed flatten (C5b); today it holds **0**
with 0 open orders, so C6's *condition* is observably met. Whether the **C6 post-containment snapshot
was captured and custodied** was **not verified** here — **unresolved evidence**.

---

# C. Activation matrix — 7 / 8 / 9

⛔ Requirements are **not** inferred across strategies merely because all three consume factor data.

| requirement | 7 sector-rotation | 8 low-volatility | 9 combined-book |
|---|---|---|---|
| factor readiness | **SATISFIED** (GREEN) | **SATISFIED** (GREEN) | **SATISFIED** (GREEN) |
| activation cooldown | **SATISFIED** (elapsed 08-10) | **SATISFIED** (elapsed 08-24) | **SATISFIED** (elapsed 07-13) |
| `has_pending_reload` | **NOT APPLICABLE** (§D) | **NOT APPLICABLE** (§D) | **NOT APPLICABLE** (§D) |
| governing incident / freeze | **OPEN** — SEC-001 conformance incident OPEN | — | ⚠ **UNRESOLVED EVIDENCE** — freeze asserted in working notes only |
| construction deployable | **OPEN** — §6: frozen V2 is *not* deployable | — | ⚠ **UNRESOLVED** — surface not read |
| approved activation authority | **OPEN** — V3 (G1, G6) not approved | **REQUIRES OWNER DECISION** | ⚠ **NOT ESTABLISHED IN THIS RECONCILIATION** |
| Track B (§21.5 cost-basis) | not applicable | **OPEN** — B1–B3 unresolved, gates activation | not applicable |
| G2 / G3 / G5 / G6 / G7 | not applicable | **OPEN** | not applicable |
| G4b disposal reachability | not applicable (0 positions) | **SATISFIED** (reachability only) | not applicable |
| full S8.6 rerun | not applicable | **NOT APPLICABLE** — no surviving consumer | not applicable |
| post-containment custody (C6) | ⚠ **UNRESOLVED EVIDENCE** | — | — |

⚠⚠ **A gap of the same class strategy 7 had — and it must not be papered over.** **Strategy 9's
custodied activation surface was not located or read in this session.** Its "FROZEN / NO-GO" status is
carried from **working notes only**, not from any custodied document verified here.

⛔ **Do NOT record FROZEN / NO-GO in this reconciliation as a verified governance ruling.** It is
**unresolved evidence**. The correct fail-closed statement, and the only one this document makes, is:

> **Strategy 9 — `IDLE / activation authority NOT ESTABLISHED IN THIS RECONCILIATION`.**

⏭ **Lane E follow-up (not this PR):** locate strategy 9's actual custodied activation authority before
any future activation classification is made for it.

⭐ **No strategy has a clear path.** Each of the three carries at least one OPEN blocker or
unresolved-evidence item that is entirely its own.

---

# D. `has_pending_reload` — semantics determined

**Classification: INFORMATIONAL / deployment-induced bookkeeping. NOT an activation gate and NOT an
execution blocker.**

**Custodied definition** — `app/db/models/strategy.py`:

> *"P4 §4: hot-reload signaling. `has_pending_reload` flips True when the StrategyFileWatcher detects
> a modification to the underlying `code_path`. The user clears it by calling `POST /reload` (which
> also re-imports the module)."*

**Complete reader/writer census at `b94838b6`** (excluding tests):

| site | role |
|---|---|
| `services/strategy_file_watcher.py:160` | **writes True** on file modification |
| `api/v1/strategies.py:509–510` | **writes False** — the `POST /reload` endpoint |
| `api/v1/schemas/strategies.py:96` | response field — **display only** |
| *(nothing else)* | — |

⭐ **No activation, dispatch, engine, or risk path reads it.** It gates nothing.

**Runtime corroboration.** All ten strategies carry `has_pending_reload = 1` with `pending_reload_at`
= **`2026-08-28 23:11:26`**, within **48 ms** of each other — matching the app-tree mtime
`2026-08-28 19:11:26 EDT`. A deployment rewrote the template files and the watcher flagged every
strategy at once. **Strategy 1 trades normally in `PAPER` with the flag set**, which is direct
contrary evidence against treating it as any kind of execution blocker.

## ⛔ Correction — the flag is NOT the subject of the one-runtime-epoch rule

An earlier note in this session treated `has_pending_reload = 1` as an activation prerequisite under
the one-runtime-epoch/reload rule. **That conflated two different things:**

- the **flag** records that a reload is **outstanding** (the file changed and was never re-imported);
- the **governance rule** concerns whether a reload that was **performed** still counts after a
  restart.

⇒ The flag assigns **no activation credit and no debit**. ⛔ Do **not** clear `has_pending_reload` or
perform a reload on any strategy. The one-runtime-epoch rule's applicability to a *future* activation
remains a separate question, and is **not** answered by this flag.
