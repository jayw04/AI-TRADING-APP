---
name: audit-log
description: Use when working on the audit log, the hash chain, the AuditLogger API, audit-related migrations, or adding new AuditAction enum values. This includes files under apps/backend/app/audit/, apps/backend/app/observability/audit_hash.py, the audit_log table and its triggers, and scripts/verify_audit_integrity.py. Also invoke this skill when reviewing or modifying tests under apps/backend/tests/audit/ or when working on the on-call playbook scenarios.
---

# Audit Log Conventions

The audit log is the platform's forensic record. It is the answer to "what happened" when something goes wrong, the proof when a user disputes a charge, the evidence in a tax audit. It is also the user-facing trust artifact — knowing that nothing can be quietly modified is part of why the platform is differentiated.

This skill governs every change that touches the audit subsystem. The rules below are not "good practice"; they are properties the platform depends on.

## Properties the audit log must preserve

### Append-only at the database level

The `audit_log` table has SQL triggers — `audit_log_no_update` and `audit_log_no_delete` — that block any `UPDATE` or `DELETE` operation. These triggers are not optional; they are how the platform proves the log was not modified. If you need to "clean up" audit entries for any reason (test environments, debugging), the answer is to recreate the database, not to disable the trigger.

The triggers exist in every environment, including local development. Muscle memory matters; if you bypass the trigger in dev, you will eventually bypass it in production.

### Hash-chained

Each row includes `row_hash` (SHA-256 of the row's content) and `prev_hash` (the `row_hash` of the immediately prior row, ordered by `id`). The first row's `prev_hash` is the zero hash. Verification walks the chain and confirms each `prev_hash` matches the previous row's `row_hash`; if any row was modified after insertion, the chain breaks at the modification point.

Computing the hash uses `compute_row_hash()` in `app/observability/audit_hash.py`. The function signature is stable; do not modify it. If the hash algorithm ever needs to change (it shouldn't), it requires an ADR and a migration strategy for verifying historical entries.

### Typed actions

Every entry has an `AuditAction` enum value. The enum is the closed set of things that can be audit-logged. Adding new actions requires:

1. Adding the enum value in `app/db/enums.py`
2. Adding the corresponding `AuditLogger.<action>()` method or extending the generic `AuditLogger.record()` API
3. Adding the action to the on-call playbook (`docs/runbook/on-call.md`) if it represents a scenario an operator might investigate
4. Updating any frontend i18n for human-readable action descriptions

Skipping any of these creates audit entries that work in code but confuse operators. The playbook is part of the surface area.

### Stable payload schema

The `payload` JSON column is structured. Each `AuditAction` has an associated payload shape; the shape is documented in `app/audit/payload_schemas.py`. Changes to the payload shape for an existing action are backwards-incompatible — old entries in the database have the old shape and cannot be retroactively migrated (the immutability triggers see to that). If a new field is needed, prefer adding it (with a default for old entries) over changing existing fields.

When in doubt, version the action: `STRATEGY_PROPOSAL_GENERATED_V2` rather than modifying `STRATEGY_PROPOSAL_GENERATED`'s shape. This is verbose, and it is correct.

### The AuditLogger API

Callers do not write to the audit log directly. They go through `AuditLogger` (introduced in PR #15, in `app/audit/audit_logger.py`). The logger:

1. Validates the action and payload against the schema
2. Computes the row hash, including the previous row's hash
3. Inserts the row in a transaction
4. Returns the inserted row's ID for caller convenience

Direct SQL inserts into `audit_log` bypass the hash chain computation. Even in tests, prefer the `AuditLogger` API; if a test needs raw inserts, use a documented test fixture rather than ad-hoc SQL.

## When you are asked to add a new audit action

Walk through this:

1. **Confirm the action belongs in the audit log.** The bar is "would a forensic auditor reconstructing what happened need this entry?" Routine UI navigation, read operations, and ephemeral state changes generally don't qualify. Anything that changes account state, modifies a strategy, submits an order, rotates a credential, or changes a risk limit does.

2. **Add the enum value** in `app/db/enums.py`. Name it descriptively: `STRATEGY_PROPOSAL_APPROVED`, not `PROPOSAL_OK`. Audit-log entries are read months or years later; the name should be self-explanatory.

3. **Define the payload schema** in `app/audit/payload_schemas.py`. Include all fields that future-you would want to see when investigating.

4. **Add the `AuditLogger` method** or extend the generic API. The method signature should make incorrect usage hard — typed parameters, required fields enforced.

5. **Wire it into the caller** at the moment the action happens, not before (you'd log an attempt rather than the action) or after (you might miss it on the error path). The audit entry is part of the action's transaction; if the action fails, the audit entry should not be written.

6. **Update the on-call playbook** if the action represents a scenario operators might investigate. Add a section like "User reports `STRATEGY_PROPOSAL_REJECTED` they didn't make."

7. **Add tests** that confirm the action fires when expected, with the expected payload shape.

## When you are asked to modify the audit subsystem itself

This is the highest-stakes area in the codebase. The hash chain integrity is what makes the audit log trustworthy; modifications to the hash function, the schema, or the immutability triggers break that trust in ways that may not be detectable for a long time.

Before any change to `app/observability/audit_hash.py`, the trigger definitions, or the core `AuditLogger` flow:

1. **Confirm the change has an ADR backing it.** If not, ask for one before proceeding. Audit subsystem changes are not "implementation details."

2. **Plan the verification strategy.** How will you confirm that existing audit entries are still verifiable after the change? Existing entries cannot be modified; the verification logic must continue to work for them.

3. **Run the integrity verification script before and after.** `scripts/verify_audit_integrity.py` should report "Verified N rows; 0 errors" both pre- and post-change.

4. **Walk away for at least 2 hours** before merging. The audit subsystem is where rushed decisions cause damage that surfaces months later.

## The on-call scenarios

The on-call playbook (`docs/runbook/on-call.md`) lists scenarios paired with audit-log queries that diagnose them. When adding a new action, consider whether the playbook needs a new scenario. A typical playbook scenario:

```markdown
## "Strategy stopped trading unexpectedly"

Check the audit log for recent actions on the affected strategy:

  SELECT created_at, action, payload FROM audit_log
  WHERE payload->>'strategy_id' = '<id>'
  ORDER BY id DESC LIMIT 20;

Look for:
- STRATEGY_DEACTIVATED — user or system deactivated the strategy
- STRATEGY_HALTED — risk gate halted the strategy
- CIRCUIT_BREAKER_TRIPPED — account breaker tripped, halting all strategies
- STRATEGY_PROPOSAL_PROMOTING — new variant in cooldown, old variant paused

Investigation continues based on which action is present.
```

The playbook is the document that turns the audit log from raw data into operational knowledge. Keep them in sync.

## Patterns to avoid

- **"Just for this test, let me UPDATE an audit_log row directly"**. The trigger will block it (correctly). If you need a different audit-log state for a test, build it through `AuditLogger` calls or use a test fixture that creates the desired chain from scratch.

- **Inferring fields from context rather than passing them explicitly**. An `AuditLogger.record_order_submitted()` call that infers the user from a thread-local is fragile and untestable. Pass the user explicitly. Verbosity in audit-related code is a feature.

- **Wrapping `AuditLogger` calls in `try/except` that swallows errors**. If the audit log can't be written, the action should not proceed. Audit failures are real failures. The integrity of the chain depends on entries not being silently dropped.

- **Modifying historical entries via migration**. Migrations can add columns (with defaults) and can add new tables. They cannot modify the content of existing `audit_log` rows. If you find yourself wanting to "backfill" historical audit data, the right answer is usually a new table or column, not a backfill.

- **Forgetting the cascading writes**. Some actions trigger multiple audit entries — a strategy promotion writes `STRATEGY_PROPOSAL_APPROVED` and then, after the cooldown, `STRATEGY_PROMOTED`. The hash chain handles this naturally (each entry chains to the prior), but the caller has to remember to write both. Read the on-call playbook scenarios when adding a new flow to confirm you've covered all the expected entries.

## What "good" looks like in this domain

An audit-log PR that lands cleanly typically has:

- A new `AuditAction` enum value with a clear, descriptive name
- A payload schema in `app/audit/payload_schemas.py`
- A typed `AuditLogger` method (or a clear use of the generic API)
- Tests confirming the action fires with the expected payload
- An on-call playbook scenario if operators might investigate it
- The integrity verification script still reporting zero errors
- A walk-away gap of at least 1 hour (longer for changes to the subsystem itself)

Audit subsystem PRs are the area where over-engineering is appropriate. Verbose schemas, explicit fields, paranoid tests — all of these are virtues here.
