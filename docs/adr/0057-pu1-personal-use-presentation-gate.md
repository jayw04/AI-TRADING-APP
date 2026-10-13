# ADR 0057 — PU-1 personal-use presentation gate

| Field | Value |
|---|---|
| Date | 2026-10-12 |
| Status | Draft — becomes Accepted on owner approval of this PR |
| Phase | Cross-phase (labeling and export control only; no order-path or data-path change) |
| Supersedes | — |
| Related | 0002 (single OrderRouter), 0006 v2 (no LLM in order path), 0037 (EAD licence flags), 0043 (governed harnesses, sealed digests), 0051 (mini-ADR precedent: a rule enforced by mechanism rather than diligence) |

> Numbering note: 0052–0054 are reserved or held by in-flight workstreams (see ADR 0055). 0057 is the
> next free number after 0056, not a skip.

## Context

Market data the platform consumes is licensed. The owner's reading (recorded as a reading, not as a
legal conclusion) is that Alpaca's Terms & Conditions and the NYSE Market Data Display Services
Agreement permit personal, non-commercial use and local storage, but restrict furnishing the data to
others, and treat *derived* data as Market Data. Anything that leaves the owner's private working set
(a deck, a printed report, a share folder, a customer-facing page) is therefore a licensing event, and
today nothing in the platform distinguishes a personal-use number from a presentable one. The mistakes
this rule prevents are not made at the keyboard of a careful reader; they are made at 11pm assembling a
deck.

Three weaknesses had to be closed together: labels can be forgotten, a gate can be bypassed by a
new export path added beside it, and a new data source can enter ingestion without anyone having read
its terms.

## Decision

1. **Every governed artifact carries a licence scope** — `license_scope` (`COMMERCIAL_OK`, `UNKNOWN`,
   `PERSONAL`) with `license_sources`, placed in the envelope next to `artifact_sha256`. Scope is
   *recomputed* from the sources via the registry; a producer can only tighten, never loosen.
   Taint propagates: the scope of a derived artifact is the most restrictive scope of its inputs, so a
   join, resample or backtest cannot launder it.
2. **The presentation gate is fail-closed with no override.** Only `COMMERCIAL_OK` passes. `UNKNOWN`
   (including unregistered sources, missing tags, an empty lineage and an unreadable registry) is
   treated as `PERSONAL`. There is no parameter, flag or environment variable that suppresses the gate
   or the fixed footer; the single route to presentability is a reviewed registry change.
3. **Pinned envelopes are never re-serialised.** Factor-coverage receipts, governed-corpus manifests
   and ADR-0043 records have pinned digests; adding a field would change them. For those, the scope is
   recorded in a sidecar `<artifact>.license.json` bound to the artifact's own SHA-256. The sidecar
   governs; a missing, unreadable or digest-mismatched sidecar is `UNKNOWN`, and an in-envelope label
   is never trusted over it.
4. **Three CI checks make the rule structural** (all in the LIGHT block, stdlib only; a fourth, the
   required-test verifier, runs in FULL):
   a. *Export-path closure* — `check_pu1_export_path_closure.py` against
      `apps/backend/ci/pu1_export_paths.json`. Every function that writes, renders or targets an
      outbound path (precise definition in the script) must be `GATED` or `INTERNAL_ONLY` with a
      reason; an unlisted one fails the build, so a new export path cannot skip the gate unnoticed.
   b. *Registry closure* — `check_pu1_registry_closure.py` against `apps/backend/ci/pu1_source_map.json`.
      Every data host, vendor-SDK namespace and snapshot module reached by ingestion code must map to
      a row in the licence registry; an unregistered source fails the build, not just runtime.
   c. *Required gate tests* — `apps/backend/ci/pu1_required_tests.json` (`--phases pu1`): PERSONAL,
      UNKNOWN and missing tags blocked; sidecar over envelope; propagation through join, resample and
      backtest; footer present and non-suppressible; `COMMERCIAL_OK` passes. A removed, renamed or
      skipped test fails CI. The existing `check_pu1_presentation_gate.sh` (leaf package, order path
      never imports it, no rendering library outside the seam) is wired alongside.
5. **Registry content.** `alpaca_market_data` (renamed from `alpaca_sip`) is `PERSONAL` and covers
   *every* Alpaca market-data feed (sip, iex, delayed_sip, any other, bars/trades/quotes); the feed
   mapping is total, so no feed is `UNKNOWN`-by-accident. Its basis records, as structured data, the
   two documents (hash `null` with status `PENDING_OWNER_SUPPLIED_AS_FETCHED_2026-10-12` — no hash is
   fabricated), the owner's reading, the re-check triggers and the ruling reference. `sharadar`, `fmp`
   and `quiver` stay `UNKNOWN`; `sec_edgar`, `usaspending` and `fred` are registered `UNKNOWN` so the
   build-time closure passes without anyone asserting terms nobody has read. Public accessibility
   alone does not establish a commercial-use classification: `sec_edgar`, `usaspending` and `fred`
   stay `UNKNOWN` and are resolved in a later bounded task.
6. **First `COMMERCIAL_OK` entry: `owner_generated_records`** — the owner's own account, order,
   gate-refusal and operational records, "owner-generated operational records; contains no vendor
   market data". A metric that touches market data (slippage against quotes, fill quality, P&L marked
   to market) carries the market-data source and stays `PERSONAL` by taint. The validator requires a
   `COMMERCIAL_OK` entry to carry a dated basis, an owner ruling, and a SHA-256 on every listed
   document (or an explicit statement that no vendor document applies).
7. **Status changes are reserved to the owner**, and only when the owner believes the application can
   be used commercially. No agent, script or configuration moves a source to `COMMERCIAL_OK`; a recheck
   trigger (document hash change, commercial use, an account moving to an entity) reopens the entry.
8. **The Evidence page declares scope per panel** (confidence, KPIs, research programs, strategy
   books), not per KPI type or view. Each panel and KPI row carries its own `license_scope`,
   `license_sources` and footer; the top level is the combined most-restrictive scope; Print is
   enabled only when every visible panel is explicitly `COMMERCIAL_OK` (a missing field is blocked).

9. **The Alpaca broker/trading API is a MIXED source, classified per field.** An order id, a
   quantity and the owner's cash balance are the owner's operational records; `market_value`,
   `current_price`, `unrealized_pl*`, `change_today`, `lastday_price` and marked-to-market account
   equity are market data — and they arrive in the same response. The two broker hosts and the
   `alpaca.trading` SDK are therefore `MIXED` in `ci/pu1_source_map.json` (not blanket `NON_DATA`),
   pointing at `app/licensing/broker_field_classification.json`. `OWNER_RECORD` fields map to
   `owner_generated_records`; `MARKET_DATA` fields map to `alpaca_market_data`; any field or response
   kind the table does not name is `MARKET_DATA` (conservative), an unreadable table classifies
   everything `MARKET_DATA`, and consuming no fields at all is an empty lineage (`UNKNOWN`). The
   helper `app.licensing.broker_fields` returns the sources/scope of the subset of fields a derived
   artifact actually consumed (`sources_of_fields`, `scope_of_fields`, `subset_with_lineage`,
   `taint_from_fields`, `field_license_block`). The registry-closure check enforces, by AST, that a
   module reading one of the table's enforced market-data field names (`market_value`,
   `current_price`, `unrealized_pl`, `unrealized_plpc`, `change_today`, `lastday_price`,
   `portfolio_value`, `last_equity`, `buying_power`, ...) calls the helper or is listed with a
   reason. Own fill prices, average entry price and cost basis are classified `OWNER_RECORD` (the
   owner's transaction record) with `review: true`: **an owner ruling on treating own execution
   prices as owner records is pending**, and a derived metric that compares them to a quote carries
   the market-data source by taint. Order-path extraction points (risk engine, router, broker
   adapters) and ADR-0042/0043 harnesses are *classified by the table only* and are not edited
   (`app/brokers`, `app/risk`, `app/orders` must not import `app.licensing`).
10. **Evidence lineage is traced per KPI row, not asserted per panel** (`app/licensing/evidence_lineage.py`,
    each input with a file:line trace). A row's sources are the union of its inputs' sources; the
    panel is the most restrictive of its rows; taint is never removed to make a panel presentable.
    Finding: `replay_consistency` is **not** an owner-records-only row. Replay recomputes the
    circuit-breaker trip from the audit fingerprint (`net_pnl = realized_pnl_today +
    unrealized_pnl_now`), and `unrealized_pnl_now` is `SUM(positions.unrealized_pl)`, a broker
    marked-to-market field. The replay counters cannot be split by decision type, so the ratio, and
    every panel that consumes the replay counters (confidence), carry `alpaca_market_data` and are
    `PERSONAL`; the other KPI rows stay `COMMERCIAL_OK`.
11. **Evidence reports are INTERNAL.** `monthly_evidence`, `live_evidence`, `confidence_score`,
    `ops_kpis`, `edge_evidence` and `range_evidence` write through the shared writers
    (`write_internal_report` / `write_internal_json`) with sources declared from their actual reads,
    carry the PU-1 footer and a scope sidecar, and are `INTERNAL_ONLY` in the export-path registry
    until content and source basis support presentation. The previous "customer-facing" /
    "allocator-readable" wording was removed (wording only), and each report states that a
    presentation label or sidecar does not establish permission to share it.

## Rationale

Alternatives considered:

- **Documentation and a reviewer checklist only.** Rejected: this is the failure mode the rule exists
  for. A checklist does not fail a build.
- **Re-serialise every envelope with a `license_scope` field.** Rejected for pinned artifacts: it
  changes sealed digests, which the platform never does retroactively. The sidecar gives the same
  guarantee without touching a byte.
- **A per-call `allow_personal=True` override "for the board deck".** Rejected on the same grounds as
  every bypass in CLAUDE.md: it grows into the normal path. The registry edit is the override, and it
  is slow on purpose.
- **Per-feed registry rows (`alpaca_sip`, `alpaca_iex`, ...).** Rejected: the owner's reading does not
  distinguish feeds, and an unlisted feed becoming `UNKNOWN`-by-accident hides the real reason it is
  blocked.
- **Gating by AST export-path closure vs by runtime interception.** Closure is chosen because it fails
  the PR that adds the path; runtime interception would only fail the first user to hit it.

## Implementation notes

- Package `apps/backend/app/licensing/` (leaf; imports no order-path module); registry
  `data_license_registry.json` hash-pinned by `REGISTRY_SHA256`.
- Checks: `apps/backend/scripts/check_pu1_export_path_closure.py`,
  `check_pu1_registry_closure.py`, `check_pu1_presentation_gate.sh`; data files
  `apps/backend/ci/pu1_export_paths.json`, `pu1_source_map.json`, `pu1_required_tests.json`.
- Broker-field classification: `app/licensing/broker_field_classification.json` +
  `app/licensing/broker_fields.py`; Evidence lineage: `app/licensing/evidence_lineage.py`; the
  broker-field AST rule and its allowlist live in `check_pu1_registry_closure.py` /
  `ci/pu1_source_map.json` (`broker_field_access`). Wired surfaces: `/api/v1/evidence/summary`,
  `/api/v1/positions`, `/api/v1/account`, `scripts/live_evidence.py`, `scripts/reports/daily_report.py`.
- The AST check does not see non-Python export paths other than the frontend print trigger (a text
  rule over `apps/frontend/src`); shell scripts are out of scope.
- **What the export-path closure does not prove.** It is a deterministic by-name AST rule, not a
  proof that no byte can leave. It detects: direct and referenced writer attributes
  (`w = p.write_text; w(x)`), `getattr(o, "write_text")` with a literal name, `open`/`io.open`/
  `gzip.open`/... and simple aliases, an `open` with a non-literal mode, subprocess/`os.system`
  commands whose literal text redirects (`>`, `>>`, `tee`), a fixed list of third-party egress
  method names (`put_object`, `upload_file`, `sendmail`, ...), literal `importlib.import_module` /
  `__import__` of a rendering library, and constant-folded or path-builder-assembled outbound
  segments. It does **not** prove, and tests assert it does not detect: non-literal `getattr` /
  `import_module` names or any path built from variables; a subprocess command assembled at run
  time; writing through a third-party client under a method name outside the list, or an HTTP
  client body (requests/httpx/urllib); redirection performed outside Python (`> report.md`, a
  scheduled-task wrapper) and any non-Python script; `exec`/`eval` of generated code; writes by
  method name on an instance the check cannot type. A new covered route is added to
  `DETECTED_BYPASSES`, a newly understood gap to `UNCOVERED_BYPASSES`, in
  `tests/licensing/test_pu1_ci_checks.py`. The same honesty applies to the broker-field rule: it
  does not catch dynamic `getattr`, constructed keys, keyword arguments, dict-literal keys,
  `model_dump()` of a third-party object, or the un-enforced `equity`/`cash` names, and a helper
  call anywhere in a module satisfies the rule for the module without proving each access is
  routed through it.
- `check_pu1_export_path_closure.py` lists internal research writers and sealed/frozen writers as
  `INTERNAL_ONLY` with a reason **without editing them**.

## Consequences

- **Positive**: a personal-use number cannot reach a presentation path through any new code without a
  failing build; the first presentable surface (owner records) exists and is provably free of market
  data; scope of every Evidence panel is visible.
- **Negative**: every new writer needs a registry line; every new ingestion host needs a map line and a
  registry row; the `INTERNAL_ONLY` list is a judgement list that reviewers must read. Panels that mix
  owner records with market data are `PERSONAL` as a whole unless split.
- **Neutral**: no change to what is fetched, stored, computed or traded.

## What this ADR does not change

Frozen specifications, validation partitions, sealed digests, the strategy code, the order path
(`OrderRouter`, risk engine, broker adapters) and the CI invariants listed in CLAUDE.md. The package is
a leaf and `check_pu1_presentation_gate.sh` enforces that the order path never imports it.

## Re-evaluation triggers

- Either licence document's hash changes, or a document hash is supplied for the pending entries.
- Any use becomes commercial, or any account trading on these signals moves to an entity.
- A vendor contract is read and `sharadar`, `fmp`, `quiver`, `sec_edgar`, `usaspending` or `fred` is
  reclassified (owner only).
- A new presentation surface (deck, PDF, public page) is built: it must route through the seam and be
  added to the export-path registry in the same change.
