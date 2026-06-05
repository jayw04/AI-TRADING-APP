"""LLM-driven LIVE trading opt-in (P6b §5, ADR 0006 v2 §5).

This package is the ONE sanctioned LLM-in-order-path. It is on the
``check_no_llm_in_order_path.sh`` allowlist (the per-(user, strategy, version)
``LLM_OPT_IN_ALLOWED`` bypass the ADR describes). The bypass is gated at runtime
by an ``active`` ``llm_opt_in`` row + a version match + a per-user daily cap, and
that gating is itself enforced by CI invariant #13
(``check_llm_optin_bypass_gated.sh``). Distinct from the §4 ``eval_harness``
package (which is paper-only, invariant #12) — the live gate may submit to a
live account, but ONLY for an opted-in strategy.
"""
