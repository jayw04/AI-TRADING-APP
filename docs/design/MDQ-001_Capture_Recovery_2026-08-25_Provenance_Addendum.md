# MDQ-001 — Capture Recovery 2026-08-25: Provenance Addendum

**Program:** MDQ-001 (Market Data Quality, Phase A)
**Addends:** `docs/design/MDQ-001_Capture_Recovery_2026-08-25.md` (MERGED `5a48ee88` / #684)
**Record type:** Chain-of-custody / provenance addendum
**Status:** Final

---

## 1. Why this addendum exists

The recovery record (#684) records the 2026-08-25 stage timings — acquisition `13:25:02Z → 19:59:00Z`,
EOD `20:30:00Z → 20:30:04Z`, freeze `20:45:02Z → 20:45:08Z` — but **does not record that a backend
redeployment landed between EOD and freeze**. The v0.14 state sync (`3cf45ad2` / #688) summarizes #684
rather than duplicating its provenance detail, so it carries the same omission.

This is a **provenance omission, not an evidence defect.** It does not invalidate the 2026-08-25
partition. Neither #684 nor #688 is modified by this addendum.

---

## 2. The deployment transition

```text
13:25:02Z → 19:59:00Z   mdq-sample.service   container 349e7504… (pre-A3 deployment)
20:30:00Z → 20:30:04Z   mdq-eod.service      container 349e7504… (pre-A3 deployment)
20:40:57Z               A3 BACKEND REDEPLOY COMPLETED — container recreated
20:45:02Z → 20:45:08Z   mdq-freeze.service   container 346e2c9f… (956e932)
```

| Property | Acquisition + EOD | Freeze + verify + mirror |
|---|---|---|
| Container | `349e75043d49…` | `346e2c9f8ca8…` |
| Image | `fc76c0ed7015…` | `0453955a55c5…` |
| Deployed repository commit | pre-A3 | `956e932c8860602060b627b9c8f7966d31565337` |

The redeploy is PR **#667** — `fix(low001): resolve identity on the data frontier, and make readiness
real (v1.0.3)`. It is a **LOW-001 identity/readiness repair, not an MDQ program change.** Its
changed-file set was verified: fourteen files across `app/factor_data/store.py`, `app/universe/**`,
`strategies_user/templates/low_volatility.py` and their tests. **No MDQ collector, capture, or freeze
path was changed.**

Deployment identity at the time of writing, read live and independently:
`/opt/workbench/app/.deploy_src_sha` = `956e932c8860…` (mtime 2026-08-25 16:42:20 EDT) and
`DEPLOYED_BUILD_INFO.json` `deployed_repository_commit` = `956e932c8860…`
(`built_at_utc 2026-08-25T20:13:48Z`).

---

## 3. Continuity across the boundary

The MDQ governance tuple did **not** change across the deployment transition:

| Element | Status across the boundary |
|---|---|
| Credential identity | `credential_fingerprint b56421a28128` — unchanged |
| Account identity | `account_number PA3BGKRLH2AP` — unchanged |
| Governed acquisition identity | `collector_version mdq-collector/0.1.0`, `entitlement algo_trader_plus (account-7 login)` — unchanged |
| Partition content | 3 files per feed, both feeds; no file rewritten after freeze |
| Evidence hashes | manifest sha256 values recomputed on host and matched; host MD5 equalled the ETag returned by S3 for all six objects |

The evidence verification was performed **after** the redeploy, so the verified state is the
post-transition state. Volume comparison against the 2026-08-21 reference day remains within 0.5 % on
both feeds.

---

## 4. Conclusion

**2026-08-25 is a valid governed partition.** Its deployment provenance is **split**: acquisition and
end-of-session bar capture completed under the pre-A3 deployment, and freeze, verification, and S3
custody executed under `956e932`.

- **No credential-identity seam** was introduced.
- **No reconstruction, backfill, or re-derivation** of any captured data occurred.
- **No denominator, evidence-window, or admissibility change** follows from this addendum.
- 2026-08-24 remains a **permanent non-event** contributing zero evidence; nothing here alters it.

⚠ Recorded so that a later reader asking *"which deployment froze this partition?"* finds the answer in
the governed record rather than having to reconstruct it from container timestamps.

---

## 5. Scope

This addendum records provenance only. It does not alter D0, K1–K6, holdout definitions, Gate PX,
producer authority, the DISC-MDQ hold, or any conclusion of #684 or #688. A future ATP state sync
should **reference** this addendum rather than reproduce it.
