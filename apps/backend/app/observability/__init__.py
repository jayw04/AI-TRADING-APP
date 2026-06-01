"""Observability layer (P5 §8): audit-log hash chain, Prometheus metrics,
and structured-log credential redaction.

Nothing in here touches the order path's *behavior* — these modules add
integrity, metrics, and redaction surface area on top of the existing
code. The order router gains a metrics timer wrapper (§8.3) but the
submission logic is unchanged.
"""
