# MDQ-001 / DISC-MDQ-001 — CEE Exploratory Authorization

**Owner act, effective 2026-08-21.** Recorded **prospectively**: this authorization is committed to Git
**before** the first governed CEE partition read, so the discovery ledger cites an authorization that
predates the evidence rather than a permission documented afterwards.

**Governing plan:** ATP v1.4.1 Implementation Plan v0.13 — §4.10 (value-extraction operating rule),
§4.10.1 (evidence firewall), §4.10.7 (discovery-ledger acceptance gate), §3.2 (CEE execution-quality
fields), §6 item 25, §8 items 15 and 18.

---

## 1. Authorization

**CEE is AUTHORIZED.** The first governed CEE exploratory session may begin against the operational
DISC-MDQ discovery-ledger / read path.

**Bounded to:**

- **authorized non-holdout data only** — no held-out symbol or held-out date bytes may be opened;
- the **governed implementation-shortfall / SIP midpoint-spread reconstruction scope** (§4.10, §3.2);
- **every partition read and every condition examined recorded through the operational discovery ledger
  before / at the governed read boundary.**

### What this authorization does NOT grant

CEE is **observation / research only (L0)**. It grants **no** strategy behavior, order, broker, ranking,
admission, L1/L2, or production-trading authority.

⛔ Explicitly **not** authorized by this act:

| Not authorized | Why |
|---|---|
| The broad **DISC-MDQ feature library** | HELD pending the repeated population census (§4.10.6; owner ruling 2026-08-20) |
| **GAP** feature development | GAP ∩ MDQ = 0 on both snapshot days — observation-only, unfunded |
| Opportunistic **universe widening** | Re-scoping the enrichment population is a governed change, never a research convenience |
| **MOM-SIP-0** | Structurally NOT EVALUABLE — MOM-001 archived/IDLE, nine historical orders (§4.10 application note) |
| **Any holdout evaluation** | The graduating-hypothesis holdout test is a separate, explicit, one-time act |

### Evidence firewall (§4.10.1) — restated because it binds this work

CEE findings are **INADMISSIBLE** to K1–K6. They may not be used to change any K-criterion definition,
threshold, matching rule, tolerance, denominator, evaluability clause, or the already-recorded **PX-2**
determination (registration §8.4, signed 2026-08-20).

**K5 remains mechanically computed and reported exactly as frozen.** Its non-discriminating PASS does not
count toward the ratified **≥2 evaluable-AND-PASS GO floor**. CEE changes nothing about that.

⭐ Note the asymmetry, deliberately: CEE *reconstructs* under the **K5 matching rule** (ruling R2 —
at-or-before, max age 5 s, bounding `ref_ts − cycle_ts`) so that its measurements are comparable to the
qualification's, while its **outputs never flow back into K5**. Using the same rule is not the same as
producing qualification evidence.

---

## 2. Preconditions — satisfied before this authorization was issued

| Precondition | Evidence |
|---|---|
| Gate PX clear | All six items discharged 2026-08-20 (#649–#652) |
| Discovery ledger **built and binding** | `50efc2f` (#654) — twelve-item §4.10.7 gate discharged in code |
| Discovery ledger **OPERATIONAL on `ec2-paper`** | Acceptance PASS 2026-08-21T21:32:05Z |
| Acceptance evidence **in durable Git custody** | `e794fc7` (#656) — `docs/design/MDQ-001_Discovery_Ledger_Production_Acceptance_2026-08-21.md`, sha256 `665c306436355785e7630d4261d2727a0ab6557f3379d30b68197c5004b2163b` |
| Governed artifacts deployed and verified | holdout `7832ff38…`, universe `0c57bd71…`, both `mode 444 root:root` |
| Production ledger genesis | `/opt/workbench/data/mdq_discovery/ledger.jsonl` — `DISC-MDQ-001#1:a1aecc44b28611e8`, conditions_examined 0, partition_read 0 |

§4.10.7's hard statement is therefore satisfied: the ledger is operational **and in the read path**,
not merely built.

⚠ **§4.10.1 consequence, stated plainly.** The moment CEE opens its first frozen partition, every
unfinished governance item converts from *open* to *permanently unresolved*. The items that had to be
closed first are closed (PX-1…PX-6, ruling 3 signed, PX-2 recorded, holdout artifact stamped). This
authorization is issued in the knowledge that the firewall closes behind it.

---

## 3. The §4.10 mandatory frame

§4.10 requires every value-extraction work item to name six things. For CEE:

**Decision it could improve.** Whether the platform can measure execution quality well enough to support
a future MOM-001 **L1 execution path** — specifically decision-price selection, spread-aware order
placement, and post-trade implementation-shortfall attribution. v0.13 identifies this as the
highest-value conversion route for the ATP datasets.

**Baseline.** The IEX-only reconstruction currently available from the existing platform record: fill
prices and order timestamps from the trading database, with IEX quote context where present.

**Feature / input definition.** Offline reconstruction from **frozen, manifest-verified** MDQ partitions
under the K5 matching rule (R2): for each qualifying paper fill, the matched SIP and IEX quote snapshot,
`mid`, `spread_bps`, `quote_age_s` per the §0.4 definitions, the decision price, and implementation
shortfall against it. Symbol and date scope come from an `AuthorizedScope` produced by
`MdqExplorationPolicy.from_config()` — never from a hand-assembled list.

**Transaction-cost treatment.** Implementation shortfall is reported gross and separately net of the
modeled commission/fee treatment already used in platform evidence; spread cost is reported as a distinct
component rather than folded into a single number, so a later reviewer can see which part moved.

**Falsification / stop condition.** CEE fails to justify further work if, on the authorized population,
SIP-based reconstruction does **not** materially change measured implementation shortfall, spread, or
decision-price quality relative to the IEX-only baseline — or if the qualifying-fill population is too
small to distinguish them. **"Not evaluable on the current population" is a valid and expected outcome**
and must be recorded as such rather than worked around.

**What would justify the next governed step.** A material, direction-consistent difference across **more
than one** measure — not one convenient statistic — would justify a *prospective* pre-registration
proposal for an L1 execution-path change. It would not itself authorize any behavior change.

---

## 4. Bounded scope of the FIRST CEE session

Owner-specified sequence. The first session is deliberately **not** feature discovery.

```text
1. authorization recorded (this document, in Git custody)
2. confirm production ledger genesis / head
3. construct AuthorizedScope through from_config
4. open ONLY authorized non-holdout partition(s)
5. ledger partition-read entry
6. compute the frozen CEE measurements
7. ledger each condition + disposition
8. produce a governed CEE observation record
9. STOP
```

⛔ **Do not** extend the first session into feature exploration, additional families, ranking
experiments, or scope expansion of any kind. The question being answered is narrow: *does the governed
SIP/IEX data materially improve implementation-shortfall, spread, decision-price and execution-quality
measurement?*

---

## 5. Population

Qualifying paper fills inside the governed review window `[2026-08-19, 2026-10-18)`, restricted to the
MDQ Phase-A universe **minus** the ten held-out symbols, and excluding the period holdout
`[2026-10-06, 2026-10-18)`. The `AuthorizedScope` enforces all three; denials are retained in full and
recorded in the ledger.

⚠ The pre-window feasibility figures (≈117 in-universe fills / 30 d; 54.7–66.7 % match rates) are
**INADMISSIBLE** and must never be quoted as evidence toward any criterion or finding. They informed
feasibility only.

⚠ **§4.10.4 generalization limit rides on every CEE output:** the DISC ∩ MDQ population is 22 base ETFs
plus 28 top-ADV names — small and liquidity-biased **by construction**. CEE findings do not generalize to
the DISC universe or to the platform's tradable universe at large.

---

## 6. Unaffected operational controls

This authorization waives **no** operational control. In particular:

🛑 **The free-space / capture-availability check before the next 09:25 ET sampler
(Monday 2026-08-24) remains mandatory**, run with the deployed guard's actual formula
`floor = max(10 GiB, 20% of capacity)` and its measured byte threshold — not inferred from the current
margin. Docker and the MDQ capture root remain the same mount (`/`), and the 2026-08-21 rebuild consumed
~2.15 GB with the build cache now at 7.41 GB.

Capture continues on its frozen schedule regardless of CEE; the ledger gates research **consumption**,
never **acquisition**.

---

## 7. Disposition

```text
Ledger code                CLOSED        50efc2f (#654)
Production readiness       OPERATIONAL   acceptance PASS 2026-08-21T21:32:05Z
Acceptance evidence        IN GIT        e794fc7 (#656)
CEE                        AUTHORIZED    this record, effective 2026-08-21 — bounded as above
Broad DISC-MDQ             HELD          pending the repeated population census
```
