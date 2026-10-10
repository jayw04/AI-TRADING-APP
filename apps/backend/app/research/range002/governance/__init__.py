"""RANGE-002 governance plumbing (plan WP0.4, WP0.6, WP0.7, WP4.2, section 5.2).

The results guard, run registry, exposure ledger, holdout token and verdict
enum. No data access, no returns, no defaults for any ``P0:`` value (R9): every
decision value is read from the frozen spec through ``FrozenSpecView``.
"""
