# Owner Decision — Authorize Independent O34 Archive Qualification

| Field | Value |
|-------|-------|
| Ruling ID | ADR0043-PH0-D-BOX-O34-ACQ-QUAL-AUTH-001 |
| Decision | **APPROVED / EFFECTIVE** |
| Scope | **Independent read-only qualification** of CONSTRUCTED O3 / O4-A / O4-B candidates only |
| Parent construction | ADR0043-PH0-D-BOX-O34-ACQ-CONSTRUCT-001 |
| Construction merge | `5def3824937b85e859345f6691f2cb37b432105f` |
| Freeze body SHA-256 | `80dfd8ec6d90182cdeabaab2d1457720ca417bcd5cb1511b4dd9d77989951bb0` |
| Sqlite snapshot SHA-256 | `26bae1f5b754c4ff80e031126674d1818ae4a9a90e4faa6b36820f2690278d5b` |
| O3 hash | `53b3310c8db3cdfd3d60a2de3bec990a6eaab8864dd592afc4590e57fc9008b0` |
| O4-A hash | `3ba73e61f5e8955a184d820c0aba4ed387de453c30fc6a22d168d84074403c49` |
| O4-B hash | `e349f49465aa2689e6c24e20d6ae32286f0a447bfbcdf3b2fbbc531c656bae95` |
| Sign-off | Owner acknowledgment (Jay Wang) — typed governance acknowledgment |
| Effective date (UTC) | 2026-07-30T13:45:00Z |
| Gate execution / campaign reopen | **Not authorized** |
| D-WIRE | **Blocked** |
| Broker activity | **Not authorized** |

---

## Ruling

Independent qualification of the three candidate archives is **AUTHORIZED**. Qualification is
**read-only** and bound to the hashes above. Allowed outcomes: `QUALIFIED`,
`REJECTED_AS_NON-BINDABLE`, `INCONCLUSIVE`.

A `QUALIFIED` result does **not** reopen O3/O4 gates. It only makes archives eligible to be
named in a later campaign scope and sealed successor freeze.

## Operational cleanup

Temporary SSH SG ingress for `79.127.147.206/32` must be **removed** after qualification
access is no longer required, or assigned explicit expiry/owner. Do not leave a stale
operator-IP rule indefinitely.

*End of ADR0043-PH0-D-BOX-O34-ACQ-QUAL-AUTH-001.*
