# Operational KPI Scorecard

_Generated 2026-06-21T18:38:45.675738+00:00 · git 70fd87b · live paper book (read-only)_

> The customer-facing operational metrics — the durable complement to the P11 operator Prometheus/Grafana dashboard. Status **ok** / **watch** (reported, not alerting).

**6 ok · 0 watch · 1 n/a**

| KPI | Value | Target | Status | Detail |
|---|---|---|---|---|
| Reconciliation success | 100.0% | 99.0% | ok | 71/71 runs passed |
| Reconciliation drift | 0 count | 0 | ok | broker ⇄ local position discrepancies (target 0) |
| Replay consistency | n/a | 99.9% | n/a | 0/0 decisions reproduced |
| Risk-gate efficacy | 20.0 % rejected | 0.0 | ok | 2 rejected / 10 checked (+1 by broker) — gates demonstrably fire |
| Circuit-breaker recovery | 9.6 min | 0.0 | ok | 1 trip(s), 1 recovered, ~10 min mean |
| Fill success | 100.0% | 90.0% | ok | 7 fills / 7 orders submitted |
| Operational continuity | 100.0% | 90.0% | ok | 1/1 trading days with an equity snapshot (daily-job uptime proxy) |

_Execution/broker latency is not durably recorded — omitted rather than estimated (an instrumentation follow-on)._

_Run weekly; the KPIs strengthen as the clean operating record lengthens._
