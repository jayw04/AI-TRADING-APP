# TODO Validation — Review Additions (to fold into `TradingWorkbench_TODO_Validation.docx`)

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-15 |
| Purpose | The four sections the design review recommended adding to the TODO Validation doc. Delivered as markdown because the source is a binary `.docx` — paste/convert these into it. |
| Source review | `review comments.md` §1 (TODO Validation Review), items A–D |

---

## Known Production Risks

> Review §1.A — consolidate the risks discussed across sections into one explicit list.

These are the failure surfaces a live (or live-bound) deployment must account for. Each should map to a mitigation and, where relevant, a runbook scenario.

| Risk | Surface | Current mitigation / where handled |
|---|---|---|
| Alpaca API outage / websocket disconnect | execution + fills | orders fail closed (no assumed fill); trade-updates stream reconnects; reconciliation on resume |
| Delayed / stale market data | sizing + signals | strategy fail-open on regime proxy, HOLD on missing factor data; bar-cache freshness |
| Clock drift / cron timing | scheduling | engine cron normalization (#115/#116); **NTP dependency — see TODO** |
| Duplicate fills / reconciliation races | fills + positions | `client_order_id` idempotency; single OrderRouter; audit hash chain |
| Broker-side order rejection edge cases | execution | typed rejection → logged/continue; cooldown on STRATEGY permanent reject |
| Docker restart ordering | startup | lifespan boot sequence; strategies auto-resume; **document compose `depends_on`** |
| SQLite file locking under concurrent write bursts | persistence | WAL journal mode; write serialization — watch under heavier WS traffic |
| Anthropic API quota exhaustion | agent/advisory only (never order path by default) | LLM is out of the order path (ADR 0006 v2); advisory degrades, trading continues |
| MCP transport failures | chart-data / workbench MCP (read-only) | read-only by invariant; trading path does not depend on MCP |

---

## Disaster Recovery

> Review §1.B — recovery procedure leveraging the existing backups + audit chain. Critical before LIVE.

Ordered recovery procedure after data loss, corruption, or a host failure:

1. **Restore the latest DB backup** (verify the backup's integrity/timestamp before restoring).
2. **Reconcile positions from Alpaca** — the broker is the source of truth for *held positions and cash*; rebuild the positions table from the account snapshot.
3. **Replay / verify the audit log** — run `scripts/verify_audit_integrity.py`; the hash chain confirms the restored log was not tampered and identifies the last consistent entry.
4. **Rebuild the cache** (bar-cache / factor accessors) from source data; caches are derived and safe to discard.
5. **Verify strategy activation states** — confirm each strategy's `status` (IDLE/PAPER/LIVE/HALTED) matches intent post-restore; nothing silently re-activates.
6. **Verify kill-switch / circuit-breaker state** — confirm breakers are in the expected state and no account is unexpectedly HALTED or unexpectedly live.

> Source-of-truth note: **Alpaca** is authoritative for positions/cash/fills; the **audit log** is authoritative for *what the system decided and did*; the **DB** is the working store reconstructed from both. (This boundary is also called out in the design review §4.C — worth formalizing.)

---

## Operational Runbook Status

> Review §1.C — summarize runbook maturity (the doc references runbooks but never states their status).

| Runbook | Status |
|---|---|
| On-call | Complete |
| Live deploy | Complete |
| Broker outage | **Partial** — reconnect/reconcile steps need fleshing out |
| Kill-switch | Complete |
| DB restore | **Partial** — see Disaster Recovery above; promote to a real runbook |
| TLS issues (Norton SSL) | Complete (ADR 0017) |
| Market-session / RTH handling | **Missing** — pending the §9A Market Session Model build (design doc v0.2) |

---

## "Retry next week" wording (clarification)

> Review §1.D — the current "retry next week" phrasing can read as "a failed rebalance is hidden for 6 days."

Replace the bare phrase with the precise intent:

> **Current design intentionally suppresses repeated retries within the same scheduled rebalance window to prevent order storms. A failed rebalance is logged and surfaced; manual rebalance remains available for operator recovery and is the intended path when a window fails — the system does not silently wait six days.**

This makes clear the suppression is a *storm guard*, not a *silent swallow*: the failure is visible (logged/audited) and operator-recoverable immediately via manual rebalance.
