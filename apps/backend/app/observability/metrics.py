"""Prometheus metrics (P5 §8.3). Exposed at ``GET /metrics`` (unauthenticated;
bound to 127.0.0.1 via the P0 docker-compose binding — do not expose publicly).

Twelve metrics, chosen so the operator can answer the questions they actually
ask: is trading happening, is it reaching LIVE, what's active, is anything
stuck, are background jobs running, are credentials stale, how fast is
submission, is the broker flaky, is anyone failing to log in, is the audit log
growing as expected.

Counters/histograms are incremented inline from the code paths (order router,
auth, broker adapter). Gauges are snapshotted from the DB every 30s by
``app/jobs/metrics_snapshot.py`` (Prometheus gauges remember their last set
value, so the snapshot job zeroes stale label sets before repopulating).
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# --- Counters ----------------------------------------------------------------

orders_submitted_total = Counter(
    "workbench_orders_submitted_total",
    "Orders submitted, by terminal outcome, account mode, and source",
    labelnames=["outcome", "account_mode", "source"],
)

live_orders_submitted_total = Counter(
    "workbench_live_orders_submitted_total",
    "LIVE orders submitted (subset of the above, surfaced separately for alerting)",
    labelnames=["outcome"],
)

broker_api_errors_total = Counter(
    "workbench_broker_api_errors_total",
    "Errors raised by broker adapter calls",
    labelnames=["adapter", "operation"],
)

auth_failures_total = Counter(
    "workbench_auth_failures_total",
    "Authentication failures by reason",
    labelnames=["reason"],
)

# --- Gauges (snapshotted; see app/jobs/metrics_snapshot.py) ------------------

strategies_active = Gauge(
    "workbench_strategies_active",
    "Strategy count by status",
    labelnames=["status"],
)

strategies_in_cooldown = Gauge(
    "workbench_strategies_in_cooldown",
    "Strategies currently in the §6 submission cooldown",
)

circuit_breakers_tripped = Gauge(
    "workbench_circuit_breakers_tripped",
    "Accounts with a circuit breaker currently tripped",
)

pending_live_strategies = Gauge(
    "workbench_pending_live_strategies",
    "Strategies in PENDING_LIVE (within the 24h activation cooldown)",
)

background_job_last_run_seconds = Gauge(
    "workbench_background_job_last_run_seconds",
    "Seconds since the last successful run of a background job",
    labelnames=["job"],
)

credential_stale_seconds = Gauge(
    "workbench_credential_stale_seconds",
    "Seconds since the last rotation of a credential, by kind",
    labelnames=["kind"],
)

audit_log_rows_total = Gauge(
    "workbench_audit_log_rows_total",
    "Total rows in audit_log (a sanity check on growth)",
)

# P10 §2 daily gross-exposure overlay (ADR 0020). Set inline by the strategy's
# overlay tick (NOT snapshotted) — gauges remember their last value, so this is the
# book's gross after the most recent tick. The reviewer's "current / average /
# minimum gross" are all derived from this one time series in PromQL: current =
# the gauge, average = avg_over_time(...[1d]), minimum = min_over_time(...[1d]).
overlay_gross = Gauge(
    "workbench_overlay_gross",
    "Book gross-exposure target after the latest daily overlay tick, by strategy",
    labelnames=["strategy_id"],
)

overlay_actions_total = Counter(
    "workbench_overlay_actions_total",
    "Daily overlay ticks by outcome (scaled / skip_drift / skip_no_price / skip_flat)",
    labelnames=["strategy_id", "outcome"],
)

# --- Histograms --------------------------------------------------------------

order_submission_duration_seconds = Histogram(
    "workbench_order_submission_duration_seconds",
    "OrderRouter.submit wall-clock duration",
    labelnames=["outcome"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


def render() -> tuple[bytes, str]:
    """Render the default registry as Prometheus exposition format."""
    return generate_latest(), CONTENT_TYPE_LATEST
