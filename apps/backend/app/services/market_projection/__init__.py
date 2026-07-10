"""MKT-PROJ-001 — Market Projection Engine (CAP-027).

Display-only decision support: daily probabilistic UP/DOWN/NEUTRAL projection
for the broad market with a separate material-move-risk probability. Governed
by the FROZEN pre-registration
(docs/implementation/TradingWorkbench_MKT-PROJ-001_PreRegistration_v1.1.md):
primary = SPY / PRE_CLOSE_TOMORROW / PIT ATR threshold / walk-forward vs the
best pre-registered baseline / calibrated logistic regression.

Hard boundary (NFR-001, CI-enforced from §4): nothing in this package may be
imported by the OrderRouter, risk engine, ranking, sizing, execution, strategy
selection, or portfolio construction. Research Preview until a gate clears.
"""
