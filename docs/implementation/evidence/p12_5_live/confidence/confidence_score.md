# Production Confidence Score — 74/100 (Building)

_Generated 2026-06-21T18:33:36.093549+00:00 · git 70fd87b · live paper book (read-only)_

> A single 0–100 measure of how trustworthy the live book is — rises with clean operation over time, falls when the discipline visibly fails (P13.5).

## Score: **74 / 100** — Building

| Component | Weight | Score |
|---|---|---|
| Verifiability (replay + reconcile clean) | 30% | 100 |
| Safety (gates fire, breaker recovers) | 25% | 100 |
| Maturity (clean track record) | 25% | 12 |
| Operational (running, no broker rejects) | 20% | 80 |

## Why

- replay + reconciliation clean
- breaker: 1 trip(s), all recovered
- risk gate demonstrably rejects (2)
- 6-day track record

_The score is conservative by design: a new book scores low (no track record), an incident-free mature book scores high. Run weekly; it climbs as the clean record lengthens._
