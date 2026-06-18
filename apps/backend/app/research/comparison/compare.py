"""compare_experiments — A/B/C experiment comparison from the registry (§4).

Pulls each experiment's ``metrics_summary`` and tabulates a chosen set of metrics
side by side, marking the winner per metric (direction-aware: Sharpe/CAGR/IC higher
is better; turnover lower is better; max drawdown — stored as a negative fraction —
higher i.e. closer to zero is better). A productivity tool, not a gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.research.registry import ResearchStore

# Lower-is-better metrics; everything else (Sharpe, CAGR, IC, confidence,
# max_drawdown-as-negative-fraction) is higher-is-better.
_LOWER_BETTER = frozenset({"turnover", "ann_turnover", "max_drawdown_abs", "duration_ms"})


@dataclass
class MetricRow:
    metric: str
    values: dict[str, float | None]   # experiment_id -> value
    winner: str | None                # experiment_id with the best value


@dataclass
class ComparisonResult:
    experiment_ids: list[str]
    rows: list[MetricRow] = field(default_factory=list)

    def to_markdown(self) -> str:
        header = "| metric | " + " | ".join(self.experiment_ids) + " | winner |"
        sep = "|---" * (len(self.experiment_ids) + 2) + "|"
        lines = [header, sep]
        for row in self.rows:
            cells = " | ".join(
                ("n/a" if row.values.get(e) is None else f"{row.values[e]:.4g}")
                for e in self.experiment_ids
            )
            lines.append(f"| {row.metric} | {cells} | {row.winner or 'n/a'} |")
        return "\n".join(lines) + "\n"


def _extract(summary: dict[str, Any], metric: str) -> float | None:
    """Pull a metric from a (possibly nested) metrics_summary. Supports a dotted
    path 'factor.field' for nested per-factor summaries."""
    if "." in metric:
        head, tail = metric.split(".", 1)
        sub = summary.get(head)
        return _extract(sub, tail) if isinstance(sub, dict) else None
    v = summary.get(metric)
    return float(v) if isinstance(v, (int, float)) else None


def compare_experiments(
    store: ResearchStore, experiment_ids: list[str], metrics: list[str]
) -> ComparisonResult:
    """Build a metric × experiment comparison with a direction-aware winner per
    metric. Unknown experiments / missing metrics render as n/a (never crash)."""
    summaries: dict[str, dict[str, Any]] = {}
    for eid in experiment_ids:
        exp = store.get_experiment(eid)
        summaries[eid] = exp.metrics_summary if exp is not None else {}

    rows: list[MetricRow] = []
    for metric in metrics:
        values = {eid: _extract(summaries[eid], metric) for eid in experiment_ids}
        present = {e: v for e, v in values.items() if v is not None}
        winner: str | None = None
        if present:
            lower_better = metric.rsplit(".", 1)[-1] in _LOWER_BETTER
            winner = (min if lower_better else max)(present, key=lambda e: present[e])
        rows.append(MetricRow(metric=metric, values=values, winner=winner))
    return ComparisonResult(experiment_ids=experiment_ids, rows=rows)
