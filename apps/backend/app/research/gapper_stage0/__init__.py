"""GAPPER v2.1.1 Stage-0 field-sufficiency PREPARATION harness.

Built under the 2026-08-17 owner authorization: **preparation only**. This package
measures data sufficiency, funnel contrast, and reconstruction fidelity for the
Stage-0 feasibility study defined in the hash-bound design
(``docs/design/Gapper/GAPPER_Research_Design_v2_1_1.docx``,
SHA-256 ``2706c4dc…d73d``). It must never *execute* Stage 0 and never emits a
governed GO/HOLD/STOP verdict: the verdict seam (``thresholds.stage0_verdict``)
returns ``NOT_EVALUABLE`` unless an owner-supplied G4/§9 execution token is
presented (``interlock``), the §3.1 dataset contract is complete
(``dataset_contract``), and every §3.3 measurement input is present.

Boundaries (research plane):

* No network I/O anywhere in this package — all data arrives by injection
  (dataframes / paths / callables).
* No ``get_settings()`` / ``get_engine()`` singletons.
* No order-path imports (``app.orders`` / ``app.risk`` / ``app.brokers``), no
  Alpaca SDK, no LLM SDK. Enforced by
  ``tests/research/test_gapper_stage0/test_structural_boundary.py``.
* Every harness output carries write-time provenance with
  ``write_class="reconstruction"`` (``provenance``); unstamped outputs are
  invalid by construction.
"""

from __future__ import annotations

__version__ = "0.1.0"
