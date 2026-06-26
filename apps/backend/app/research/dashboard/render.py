"""Research dashboard — the research homepage (P10 Phase 2 §5).

Built last (the reviewer's sequencing): now that the registry data model is
stable, render a single Markdown view of the Research Engine's state — KPIs,
recent experiments by state + confidence, strategies by lifecycle, open Research
Alerts, and the experiment genealogy (DAG). Pure read of the registry; no compute.
"""

from __future__ import annotations

from app.research.registry import ExperimentRecord, ResearchStore


def _kpis(store: ResearchStore) -> list[str]:
    exp = store.count_by("experiments", "research_state")
    dep = store.count_by("strategies", "deployment_state")
    n_exp = store.row_count("experiments")
    go = exp.get("VALIDATED", 0)
    rej = exp.get("REJECTED", 0)
    go_pct = f"{100 * go / n_exp:.0f}%" if n_exp else "n/a"
    return [
        "## KPIs\n",
        f"- experiments: **{n_exp}** (VALIDATED {go} / REJECTED {rej} / "
        f"RESEARCH {exp.get('RESEARCH', 0)}) — GO rate {go_pct}",
        f"- strategies by deployment: PAPER {dep.get('PAPER', 0)} · CANARY {dep.get('CANARY', 0)} · "
        f"LIVE {dep.get('LIVE', 0)} · RETIRED {dep.get('RETIRED', 0)}",
        f"- open research alerts: **{len(store.list_alerts(status='OPEN'))}**\n",
    ]


def _experiments(store: ResearchStore, limit: int) -> list[str]:
    rows = ["## Recent experiments\n",
            "| experiment | kind | state | confidence | created |",
            "|---|---|---|---|---|"]
    for eid in store.list_experiments()[:limit]:
        e = store.get_experiment(eid)
        if e is None:
            continue
        conf = "n/a" if e.confidence_score is None else str(e.confidence_score)
        rows.append(f"| `{e.experiment_id}` | {e.kind} | {e.research_state} | {conf} | {e.created_at} |")
    return rows + [""]


def _strategies(store: ResearchStore) -> list[str]:
    rows = ["## Strategies\n", "| strategy | research | deployment |", "|---|---|---|"]
    for s in store.list_strategies():
        rows.append(f"| {s.name} | {s.research_state} | {s.deployment_state} |")
    return rows + [""]


def _alerts(store: ResearchStore) -> list[str]:
    open_alerts = store.list_alerts(status="OPEN")
    if not open_alerts:
        return ["## Open alerts\n", "_none_\n"]
    rows = ["## Open alerts\n", "| strategy | metric | value | threshold | recommends |", "|---|---|---|---|---|"]
    for a in open_alerts:
        rows.append(f"| {a.strategy_id} | {a.metric} | {a.value} | {a.threshold} | {a.recommended_action} |")
    return rows + [""]


def _lineage(store: ResearchStore, limit: int) -> list[str]:
    """Experiment genealogy: parent → child chains via parent_experiment_id."""
    exps: list[ExperimentRecord] = [store.get_experiment(e) for e in store.list_experiments()[:limit]]  # type: ignore[misc]
    exps = [e for e in exps if e is not None]
    children: dict[str, list[str]] = {}
    have = {e.experiment_id for e in exps}
    roots = []
    for e in exps:
        if e.parent_experiment_id and e.parent_experiment_id in have:
            children.setdefault(e.parent_experiment_id, []).append(e.experiment_id)
        elif not e.parent_experiment_id:
            roots.append(e.experiment_id)
    if not children:
        return ["## Experiment lineage\n", "_no parent/child links yet_\n"]
    out = ["## Experiment lineage (DAG)\n"]

    def walk(eid: str, depth: int) -> None:
        out.append(f"{'  ' * depth}- `{eid}`")
        for c in children.get(eid, []):
            walk(c, depth + 1)

    for r in roots:
        walk(r, 0)
    return out + [""]


def render_dashboard(store: ResearchStore, *, limit: int = 25) -> str:
    """Render the full dashboard Markdown from the registry."""
    parts = ["# Research Engine — dashboard\n",
             "_Auto-generated from the research registry (read-only)._\n"]
    parts += _kpis(store)
    parts += _experiments(store, limit)
    parts += _strategies(store)
    parts += _alerts(store)
    parts += _lineage(store, limit)
    return "\n".join(parts) + "\n"


def write_dashboard(store: ResearchStore, path: str, *, limit: int = 25) -> str:
    from pathlib import Path
    text = render_dashboard(store, limit=limit)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")
    return path
