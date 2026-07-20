"""ADR 0043 — the loss-control architecture package.

This package houses the durable loss-control machinery that succeeds the ADR 0042
fast-track: a shared account-level state machine, the immutable session baseline, the
three-field trip taxonomy, the recovery preflight, and the asymmetric re-arm policy.

PR 1 (this increment) lands the persistence foundation only — the constants vocabulary
here plus the five ORM models in ``app/db/models/`` — with **no behavior change**. Nothing
in the order path consults any of it yet. The pure state machine, the persistence service,
the baseline lifecycle, the engine wiring, and the recovery preflight arrive in later
increments (see ``docs/adr/0043-loss-control-architecture.md``).
"""
