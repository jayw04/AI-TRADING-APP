from fastapi import APIRouter

from app.api.v1 import (
    account,
    accounts,
    activation,
    agent,
    agent_budget,
    alerts,
    audit,
    auth,
    backtest_jobs,
    benchmarks,
    credentials,
    discovery,
    drift,
    eval_harness,
    evidence,
    indicators,
    insider_reference,
    internal,
    journal,
    live_autodispatch,
    llm_opt_in,
    market_data,
    morning_brief,
    opportunities,
    ops,
    orders,
    positions,
    proposals,
    range_execution,
    range_insight,
    range_levels,
    range_template,
    risk,
    scanner,
    signals,
    strategies,
    strategy_authoring,
    trading_profile,
    users,
    variants,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(credentials.router)
# P5.5 §3: read-only audit feed (scoped to the current user). Powers the
# workbench-mcp audit tool + the CLAUDE.md cost/overnight decision-tree rows.
api_router.include_router(audit.router)
api_router.include_router(account.router)
api_router.include_router(accounts.router)
api_router.include_router(benchmarks.router)
api_router.include_router(internal.router)
api_router.include_router(orders.router)
api_router.include_router(positions.router)
# Trade Journal: the user's filled trades + a free-text note per trade.
api_router.include_router(journal.router)
api_router.include_router(market_data.router)
api_router.include_router(indicators.router)
api_router.include_router(users.router)
# P5.5 §1: trading-profile router prefixes /users/me; the /api/v1 prefix is
# already on api_router, so include with no extra prefix.
api_router.include_router(trading_profile.router)
# P5.5 §2: morning brief (prefix=/morning-brief). No extra prefix here.
api_router.include_router(morning_brief.router)
api_router.include_router(alerts.router)
api_router.include_router(strategies.router)
api_router.include_router(signals.router)
api_router.include_router(backtest_jobs.router)
api_router.include_router(opportunities.router)
api_router.include_router(insider_reference.router)
# P11 §1: read-only operational state (/ops/state) — what's enabled/running today.
api_router.include_router(ops.router)
api_router.include_router(evidence.router)
api_router.include_router(discovery.router)
api_router.include_router(scanner.router)
api_router.include_router(range_insight.router)
# Live buy/sell/stop levels per range symbol (monitoring the Range Trader triggers).
api_router.include_router(range_levels.router)
api_router.include_router(range_template.router)
# Range Trader daily buy/sell vs. daily high/low history (date-range window).
api_router.include_router(range_execution.router)
api_router.include_router(agent.router)
# P6 §1a: agent cost-envelope check (prefix=/agent, route /budget). Distinct
# sub-path from the P3 agent chat router above; coexists under the same prefix.
api_router.include_router(agent_budget.router)
# P5 §5: risk router routes are already absolute (/risk-limits, /accounts/{id}/
# risk-state, ...); api_router already carries the /api/v1 prefix, so include
# with no extra prefix (the v0.2 doc's prefix="/api/v1" would double it).
api_router.include_router(risk.router)
# P5 §7: activation lifecycle (prefix=/strategies, same as strategies router;
# distinct sub-paths /{id}/activation, /activate, /activate/cancel, /deactivate).
api_router.include_router(activation.router)
# P6 §1b: strategy proposals. Two routers — /strategies/{id}/propose hangs
# under /strategies (alongside strategies + activation); the rest under
# /proposals. No extra prefix (api_router carries /api/v1).
api_router.include_router(proposals.strategies_router)
api_router.include_router(proposals.proposals_router)
# P6b §1b-drift: user-level drift findings list (/drift-findings). Per-strategy
# drift-check/drift-status live on proposals.strategies_router above.
api_router.include_router(drift.router)
# P6b §2c-variant: user-level in-flight paper-variant list (/variants) for the
# Dashboard widget. Per-strategy variant-comparison lives on strategies_router.
api_router.include_router(variants.router)
# P6b §4 (ADR 0006 v2): eval-harness start/stop/read. Off the P2 gate.
api_router.include_router(eval_harness.router)
# P6b §4.5 (ADR 0015): global live-auto-dispatch master switch (/system/...).
api_router.include_router(live_autodispatch.router)
# P6b §5 (ADR 0006 v2 §5): LLM-driven live trading opt-in (/strategies/{id}/llm-*).
api_router.include_router(llm_opt_in.router)
# P7 §2: NL → Python strategy generation (POST /strategies/author).
api_router.include_router(strategy_authoring.router)
