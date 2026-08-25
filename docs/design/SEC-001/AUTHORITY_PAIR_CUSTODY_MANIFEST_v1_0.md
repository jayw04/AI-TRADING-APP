# SEC-001 V3 — Defect-F Authority Pair: Custody Manifest v1.0

Custody of the **authority pair** for the Defect-F repair, taken **before any code change**.

---

## Bound documents

| path | bytes | repository-byte SHA-256 (CRLF, as committed) | LF-normalized SHA-256 |
|---|---:|---|---|
| `docs/design/SEC-001/SEC001_V3_AcquisitionDefect_F_IgnoredRangeUnboundedRetention_v1_0.md` | 26,399 | `9e85913782bc00fb8a1afdc5153d634b3fb31ab54f33274b5ab5a6a66b0848b5` | — |
| `docs/design/SEC-001/TradingWorkbench_SEC001_V3_Design_Implementation_v0_4.md` | 69,148 | `bde6aa3b039807b2b4b9535fec0227fde7c4debc56abb81c40c290871c78159f` | `0208aaa832f2c5173cd2ee00a0c918683165ec1cf2a2d3814536fae9f7df65ec` |

Both are committed under `-text -diff` (see `docs/design/SEC-001/.gitattributes`) so the **committed
blob bytes are exactly the working-copy bytes**, CRLF preserved. Without that rule Git would
normalize the blobs to LF and the committed digest would be the secondary identity rather than the
stated one.

⚠ **Filename normalization.** The specification's working-tree file is still named
`…_v0_3.md` — a v0.3-era filename that was never renamed when the content advanced to v0.4. Custody
stores it under `…_v0_4.md`. **The bytes are identical** (`bde6aa3b…` before and after the rename);
only the name changed, so the filename now matches the version the document declares.

---

## Relationship between the two documents

They form an **atomic authority pair** and should be read together:

- The **ruling** states the authority: §7.1.a preserves the Defect-G lineage as a sequence; §7B
  records the §4.2.1 determination as **NOT SATISFIED** (branch 3); §7C issues
  `V3_LOCAL_BOUNDED_RECORDING_TRANSPORT_REPAIR — AUTHORIZED FOR IMPLEMENTATION AND CANARY ONLY`,
  with five normative boundaries and a mechanical canary transition condition.
- The **specification** carries that authority into the program critical path: §5.1c records the
  halted rebuild and its terminal Pass-2 result, §20 item **0a′** makes "implement §7C and prove it
  by the governed canary" the live next action with 0b gated on its PASS, and Appendix C lists the
  custodied evidence set.

Neither document is meaningful alone: the ruling without the spec has no program placement; the spec
without the ruling has no authority for the repair it schedules.

---

## What this custody does and does not do

**Does:** freeze the exact authority bytes, prospectively, before implementation begins.

**Does NOT:**

- execute the repair;
- close **Defect F** — F remains **OPEN** throughout implementation;
- authorize the successor crawl — the successor epoch remains **BLOCKED at 0/1,167**;
- spend `5b26ffa2…` — it remains **UNSPENT**;
- alter §5.1b **Q5**, which is unchanged because no coverage was produced;
- reverse the §4.2.1 verdict. The determination says the *current pinned path fails*; the ruling says
  a *specific V3-local remediation may be attempted*. Both hold simultaneously.

---

## Sealing rules that take effect on this commit

1. **The ruling is sealed.** It must not be edited when the canary finishes. Its purpose is to state
   authority and the transition condition **prospectively**. A canary PASS is recorded in a **new**
   Defect-F closure artifact referencing this sealed ruling; a FAIL is recorded in a separate failure
   artifact. Order preserved: **authority before execution → execution evidence → disposition.**
2. **v0.4 is preserved as an exact version.** Any later material design-state change becomes **v0.5**
   or an addendum, never a silent rewrite of these custodied bytes.

---

## State machine (unchanged by custody)

```
implementation complete        != F closed
unit tests pass                != F closed
synthetic streaming test pass  != F closed
governed real canary on 0000065984-14-000065 satisfying every binding requirement  = F may CLOSE
F closed                       != successor automatically started
```

The canary closure is sealed first; only then may the successor epoch authority consume
`5b26ffa2…` and start cleanly from **0/1,167**.

---

## Prior custody on this branch

| commit | contents |
|---|---|
| `4e960e2` | Snapshot custody record; Pass-1 storage forensics (sealed INTERIM) |
| `4394eef` | Pass-2 byte verification record |
| `725e737` | §4.2.1 bounded-streaming determination |
| `c95bcbe` | Pass-2 reproducibility artifacts (4 files + manifest) |
| *this*    | Defect-F authority pair (ruling + spec v0.4) |
