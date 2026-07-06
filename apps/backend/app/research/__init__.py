"""Research Engine subsystem (P10 Phase 2) — creates & validates trading ideas.

A top-level, read-only subsystem alongside the trading/risk/portfolio/data engines
(ADR 0018: never touches the order path). Owns the experiment/strategy/dataset/
feature/artifact registries, the dependency graph, and (later sessions) the
orchestrator, promotion gate, revalidation, comparison tools, and dashboard.
"""
