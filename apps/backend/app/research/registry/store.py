"""Research Engine registries (P10 Phase 2 §1).

A DuckDB-backed store holding the five registries — **strategies, features,
datasets, experiments, artifacts** — plus a **transition log** (the "why" audit
trail). The dependency graph is the foreign-key chain
``strategy → features → dataset → experiment → artifact``; ``dependencies()`` walks
it. Lifecycle is two orthogonal axes (plan §1): a **research_state**
(RESEARCH/VALIDATED/REJECTED/ARCHIVED) and a **deployment_state**
(NONE/PAPER/CANARY/LIVE/RETIRED); every change goes through ``transition()`` which
records the from/to/reason.

Read-only subsystem (ADR 0018): nothing here touches the order path. JSON-ish
fields are persisted as text (``json.dumps``) for portable, trivially-round-tripping
storage; the dataclasses hold native dicts/lists.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)

# app/research/registry/store.py → parents[3] == apps/backend (backend root).
_BACKEND_ROOT = Path(__file__).resolve().parents[3]

RESEARCH_STATES = frozenset({"RESEARCH", "VALIDATED", "REJECTED", "ARCHIVED"})
DEPLOYMENT_STATES = frozenset({"NONE", "PAPER", "CANARY", "LIVE", "RETIRED"})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS strategies (
  strategy_id VARCHAR PRIMARY KEY, name VARCHAR, category VARCHAR,
  research_state VARCHAR DEFAULT 'RESEARCH', deployment_state VARCHAR DEFAULT 'NONE',
  paper_since TIMESTAMP, live_since TIMESTAMP, retired_at TIMESTAMP,
  current_version VARCHAR, current_commit VARCHAR, owner VARCHAR, notes VARCHAR,
  created_at TIMESTAMP, updated_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS features (
  feature_id VARCHAR PRIMARY KEY, description VARCHAR, formula VARCHAR,
  parameters VARCHAR, introduced_in VARCHAR, deprecated_in VARCHAR, created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS datasets (
  dataset_id VARCHAR PRIMARY KEY, provider VARCHAR, version VARCHAR, created_at TIMESTAMP,
  coverage VARCHAR, row_count BIGINT, checksum VARCHAR, source_hash VARCHAR
);
CREATE TABLE IF NOT EXISTS experiments (
  experiment_id VARCHAR PRIMARY KEY, parent_experiment_id VARCHAR,
  created_at TIMESTAMP, duration_ms BIGINT, kind VARCHAR,
  strategy_id VARCHAR, dataset_id VARCHAR, feature_ids VARCHAR,
  git_commit VARCHAR, host VARCHAR, python_version VARCHAR, package_versions VARCHAR, seed BIGINT,
  params VARCHAR, is_window VARCHAR, oos_window VARCHAR,
  cost_model VARCHAR, pit_mode VARCHAR, survivorship_mode VARCHAR,
  metrics_summary VARCHAR, metrics_detail VARCHAR, confidence_score INTEGER,
  research_state VARCHAR DEFAULT 'RESEARCH', owner VARCHAR, notes VARCHAR
);
CREATE TABLE IF NOT EXISTS artifacts (
  artifact_id VARCHAR PRIMARY KEY, experiment_id VARCHAR,
  type VARCHAR, path VARCHAR, checksum VARCHAR, created_at TIMESTAMP, description VARCHAR
);
CREATE TABLE IF NOT EXISTS transitions (
  transition_id VARCHAR PRIMARY KEY, entity_type VARCHAR, entity_id VARCHAR,
  axis VARCHAR, from_state VARCHAR, to_state VARCHAR, reason VARCHAR, transitioned_at TIMESTAMP, actor VARCHAR
);
CREATE TABLE IF NOT EXISTS alerts (
  alert_id VARCHAR PRIMARY KEY, strategy_id VARCHAR, experiment_id VARCHAR,
  kind VARCHAR, metric VARCHAR, value DOUBLE, threshold DOUBLE,
  message VARCHAR, recommended_action VARCHAR, status VARCHAR DEFAULT 'OPEN', created_at TIMESTAMP
);
-- Phase 3 §3.0: first-class identities for portfolio configs, benchmarks, cost models.
CREATE TABLE IF NOT EXISTS portfolio_models (
  portfolio_id VARCHAR PRIMARY KEY, strategy_id VARCHAR, construction_method VARCHAR,
  weighting VARCHAR, rebalance VARCHAR, buffer VARCHAR, risk_model VARCHAR,
  turnover_model VARCHAR, capacity_model VARCHAR, params VARCHAR,
  status VARCHAR DEFAULT 'RESEARCH', created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS benchmarks (
  benchmark_id VARCHAR PRIMARY KEY, definition VARCHAR, source VARCHAR,
  rebalance VARCHAR, description VARCHAR, created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS cost_models (
  cost_model_id VARCHAR PRIMARY KEY, commission DOUBLE, slippage DOUBLE, spread DOUBLE,
  borrow_cost DOUBLE, market_impact VARCHAR, description VARCHAR, created_at TIMESTAMP
);
"""


def _now() -> datetime:
    return datetime.now(UTC)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _dumps(v: Any) -> str | None:
    return None if v is None else json.dumps(v, default=str)


def _loads(v: Any) -> Any:
    if v is None or v == "":
        return None
    try:
        return json.loads(v)
    except (TypeError, json.JSONDecodeError):
        return v


# ---- typed records ----


@dataclass
class StrategyRecord:
    strategy_id: str = ""
    name: str = ""
    category: str = ""
    research_state: str = "RESEARCH"
    deployment_state: str = "NONE"
    paper_since: datetime | None = None
    live_since: datetime | None = None
    retired_at: datetime | None = None
    current_version: str | None = None
    current_commit: str | None = None
    owner: str | None = None
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class FeatureRecord:
    feature_id: str = ""
    description: str = ""
    formula: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    introduced_in: str | None = None
    deprecated_in: str | None = None
    created_at: datetime | None = None


@dataclass
class DatasetRecord:
    dataset_id: str = ""
    provider: str = ""
    version: str = ""
    created_at: datetime | None = None
    coverage: str | None = None
    row_count: int | None = None
    checksum: str | None = None
    source_hash: str | None = None


@dataclass
class ExperimentRecord:
    experiment_id: str = ""
    parent_experiment_id: str | None = None
    created_at: datetime | None = None
    duration_ms: int | None = None
    kind: str = ""
    strategy_id: str | None = None
    dataset_id: str | None = None
    feature_ids: list[str] = field(default_factory=list)
    git_commit: str | None = None
    host: str | None = None
    python_version: str | None = None
    package_versions: dict[str, str] = field(default_factory=dict)
    seed: int | None = None
    params: dict[str, Any] = field(default_factory=dict)
    is_window: str | None = None
    oos_window: str | None = None
    cost_model: str | None = None
    pit_mode: str | None = None
    survivorship_mode: str | None = None
    metrics_summary: dict[str, Any] = field(default_factory=dict)
    metrics_detail: dict[str, Any] = field(default_factory=dict)
    confidence_score: int | None = None
    research_state: str = "RESEARCH"
    owner: str | None = None
    notes: str | None = None


@dataclass
class ArtifactRecord:
    artifact_id: str = ""
    experiment_id: str = ""
    type: str = ""
    path: str = ""
    checksum: str | None = None
    created_at: datetime | None = None
    description: str | None = None


@dataclass
class AlertRecord:
    alert_id: str = ""
    strategy_id: str | None = None
    experiment_id: str | None = None
    kind: str = ""                       # e.g. 'edge_decay'
    metric: str = ""
    value: float | None = None
    threshold: float | None = None
    message: str = ""
    recommended_action: str | None = None  # e.g. 'RETIRE_REVIEW' (owner decides — never auto)
    status: str = "OPEN"
    created_at: datetime | None = None


@dataclass
class PortfolioModelRecord:
    portfolio_id: str = ""
    strategy_id: str | None = None
    construction_method: str = ""
    weighting: str | None = None          # equal | inverse_vol | risk_parity | ...
    rebalance: str | None = None          # weekly | monthly | ...
    buffer: str | None = None             # rank-hysteresis / position buffer descriptor
    risk_model: str | None = None
    turnover_model: str | None = None
    capacity_model: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    status: str = "RESEARCH"
    created_at: datetime | None = None


@dataclass
class BenchmarkRecord:
    benchmark_id: str = ""
    definition: str = ""                   # e.g. 'SPY' | 'equal_weight_universe'
    source: str | None = None
    rebalance: str | None = None
    description: str | None = None
    created_at: datetime | None = None


@dataclass
class CostModelRecord:
    cost_model_id: str = ""
    commission: float | None = None
    slippage: float | None = None
    spread: float | None = None
    borrow_cost: float | None = None
    market_impact: str | None = None       # model descriptor (e.g. 'sqrt_adv')
    description: str | None = None
    created_at: datetime | None = None


@dataclass
class TransitionRecord:
    transition_id: str
    entity_type: str
    entity_id: str
    axis: str
    from_state: str | None
    to_state: str
    reason: str
    transitioned_at: datetime
    actor: str | None


class ResearchStore:
    """Connection + schema + typed registry/transition/dependency APIs."""

    def __init__(self, db_path: str | None = None, *, read_only: bool = False) -> None:
        raw = db_path if db_path is not None else get_settings().research_db_path
        path = Path(raw)
        if not path.is_absolute():
            path = _BACKEND_ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.con = duckdb.connect(str(path), read_only=read_only)
        if not read_only:
            self.con.execute(_SCHEMA)
        logger.info("research_store_open", path=str(path), read_only=read_only)

    def __enter__(self) -> ResearchStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self.con.close()

    # ---- record (idempotent upsert; returns the id) ----

    def record_strategy(self, rec: StrategyRecord) -> str:
        rec.strategy_id = rec.strategy_id or _new_id("strat")
        rec.created_at = rec.created_at or _now()
        rec.updated_at = _now()
        self.con.execute(
            "INSERT OR REPLACE INTO strategies VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [rec.strategy_id, rec.name, rec.category, rec.research_state, rec.deployment_state,
             rec.paper_since, rec.live_since, rec.retired_at, rec.current_version,
             rec.current_commit, rec.owner, rec.notes, rec.created_at, rec.updated_at],
        )
        return rec.strategy_id

    def record_feature(self, rec: FeatureRecord) -> str:
        rec.feature_id = rec.feature_id or _new_id("feat")
        rec.created_at = rec.created_at or _now()
        self.con.execute(
            "INSERT OR REPLACE INTO features VALUES (?,?,?,?,?,?,?)",
            [rec.feature_id, rec.description, rec.formula, _dumps(rec.parameters),
             rec.introduced_in, rec.deprecated_in, rec.created_at],
        )
        return rec.feature_id

    def record_dataset(self, rec: DatasetRecord) -> str:
        rec.dataset_id = rec.dataset_id or _new_id("data")
        rec.created_at = rec.created_at or _now()
        self.con.execute(
            "INSERT OR REPLACE INTO datasets VALUES (?,?,?,?,?,?,?,?)",
            [rec.dataset_id, rec.provider, rec.version, rec.created_at, rec.coverage,
             rec.row_count, rec.checksum, rec.source_hash],
        )
        return rec.dataset_id

    def record_experiment(self, rec: ExperimentRecord) -> str:
        rec.experiment_id = rec.experiment_id or _new_id("exp")
        rec.created_at = rec.created_at or _now()
        self.con.execute(
            "INSERT OR REPLACE INTO experiments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [rec.experiment_id, rec.parent_experiment_id, rec.created_at, rec.duration_ms, rec.kind,
             rec.strategy_id, rec.dataset_id, _dumps(rec.feature_ids), rec.git_commit, rec.host,
             rec.python_version, _dumps(rec.package_versions), rec.seed, _dumps(rec.params),
             rec.is_window, rec.oos_window, rec.cost_model, rec.pit_mode, rec.survivorship_mode,
             _dumps(rec.metrics_summary), _dumps(rec.metrics_detail), rec.confidence_score,
             rec.research_state, rec.owner, rec.notes],
        )
        return rec.experiment_id

    def record_artifact(self, rec: ArtifactRecord) -> str:
        rec.artifact_id = rec.artifact_id or _new_id("art")
        rec.created_at = rec.created_at or _now()
        self.con.execute(
            "INSERT OR REPLACE INTO artifacts VALUES (?,?,?,?,?,?,?)",
            [rec.artifact_id, rec.experiment_id, rec.type, rec.path, rec.checksum,
             rec.created_at, rec.description],
        )
        return rec.artifact_id

    def record_alert(self, rec: AlertRecord) -> str:
        rec.alert_id = rec.alert_id or _new_id("alert")
        rec.created_at = rec.created_at or _now()
        self.con.execute(
            "INSERT OR REPLACE INTO alerts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [rec.alert_id, rec.strategy_id, rec.experiment_id, rec.kind, rec.metric,
             rec.value, rec.threshold, rec.message, rec.recommended_action, rec.status,
             rec.created_at],
        )
        return rec.alert_id

    def record_portfolio_model(self, rec: PortfolioModelRecord) -> str:
        rec.portfolio_id = rec.portfolio_id or _new_id("pf")
        rec.created_at = rec.created_at or _now()
        self.con.execute(
            "INSERT OR REPLACE INTO portfolio_models VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [rec.portfolio_id, rec.strategy_id, rec.construction_method, rec.weighting,
             rec.rebalance, rec.buffer, rec.risk_model, rec.turnover_model,
             rec.capacity_model, _dumps(rec.params), rec.status, rec.created_at],
        )
        return rec.portfolio_id

    def record_benchmark(self, rec: BenchmarkRecord) -> str:
        rec.benchmark_id = rec.benchmark_id or _new_id("bm")
        rec.created_at = rec.created_at or _now()
        self.con.execute(
            "INSERT OR REPLACE INTO benchmarks VALUES (?,?,?,?,?,?)",
            [rec.benchmark_id, rec.definition, rec.source, rec.rebalance,
             rec.description, rec.created_at],
        )
        return rec.benchmark_id

    def record_cost_model(self, rec: CostModelRecord) -> str:
        rec.cost_model_id = rec.cost_model_id or _new_id("cost")
        rec.created_at = rec.created_at or _now()
        self.con.execute(
            "INSERT OR REPLACE INTO cost_models VALUES (?,?,?,?,?,?,?,?)",
            [rec.cost_model_id, rec.commission, rec.slippage, rec.spread,
             rec.borrow_cost, rec.market_impact, rec.description, rec.created_at],
        )
        return rec.cost_model_id

    # ---- get ----

    def get_portfolio_model(self, portfolio_id: str) -> PortfolioModelRecord | None:
        r = self.con.execute(
            "SELECT * FROM portfolio_models WHERE portfolio_id = ?", [portfolio_id]
        ).fetchone()
        if r is None:
            return None
        d = list(r)
        return PortfolioModelRecord(
            portfolio_id=d[0], strategy_id=d[1], construction_method=d[2], weighting=d[3],
            rebalance=d[4], buffer=d[5], risk_model=d[6], turnover_model=d[7],
            capacity_model=d[8], params=_loads(d[9]) or {}, status=d[10], created_at=d[11],
        )

    def get_benchmark(self, benchmark_id: str) -> BenchmarkRecord | None:
        r = self.con.execute("SELECT * FROM benchmarks WHERE benchmark_id = ?", [benchmark_id]).fetchone()
        return BenchmarkRecord(*r) if r is not None else None

    def get_cost_model(self, cost_model_id: str) -> CostModelRecord | None:
        r = self.con.execute("SELECT * FROM cost_models WHERE cost_model_id = ?", [cost_model_id]).fetchone()
        return CostModelRecord(*r) if r is not None else None

    def get_strategy(self, strategy_id: str) -> StrategyRecord | None:
        r = self.con.execute("SELECT * FROM strategies WHERE strategy_id = ?", [strategy_id]).fetchone()
        if r is None:
            return None
        return StrategyRecord(*r)

    def get_experiment(self, experiment_id: str) -> ExperimentRecord | None:
        r = self.con.execute("SELECT * FROM experiments WHERE experiment_id = ?", [experiment_id]).fetchone()
        if r is None:
            return None
        d = list(r)
        return ExperimentRecord(
            experiment_id=d[0], parent_experiment_id=d[1], created_at=d[2], duration_ms=d[3],
            kind=d[4], strategy_id=d[5], dataset_id=d[6], feature_ids=_loads(d[7]) or [],
            git_commit=d[8], host=d[9], python_version=d[10], package_versions=_loads(d[11]) or {},
            seed=d[12], params=_loads(d[13]) or {}, is_window=d[14], oos_window=d[15],
            cost_model=d[16], pit_mode=d[17], survivorship_mode=d[18],
            metrics_summary=_loads(d[19]) or {}, metrics_detail=_loads(d[20]) or {},
            confidence_score=d[21], research_state=d[22], owner=d[23], notes=d[24],
        )

    def set_experiment_confidence(self, experiment_id: str, score: int) -> None:
        """Set an experiment's confidence score (0–100), written by the promotion gate."""
        self.con.execute(
            "UPDATE experiments SET confidence_score = ? WHERE experiment_id = ?",
            [score, experiment_id],
        )

    def list_experiments(self, *, kind: str | None = None, strategy_id: str | None = None) -> list[str]:
        clauses: list[str] = []
        params: list[Any] = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if strategy_id:
            clauses.append("strategy_id = ?")
            params.append(strategy_id)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self.con.execute(
            f"SELECT experiment_id FROM experiments{where} ORDER BY created_at DESC", params
        ).fetchall()
        return [r[0] for r in rows]

    def list_strategies(self, *, deployment_state: str | None = None) -> list[StrategyRecord]:
        clause = " WHERE deployment_state = ?" if deployment_state else ""
        params = [deployment_state] if deployment_state else []
        rows = self.con.execute(f"SELECT * FROM strategies{clause}", params).fetchall()
        return [StrategyRecord(*r) for r in rows]

    def list_alerts(self, *, status: str | None = None, strategy_id: str | None = None) -> list[AlertRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if strategy_id:
            clauses.append("strategy_id = ?")
            params.append(strategy_id)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self.con.execute(
            f"SELECT alert_id, strategy_id, experiment_id, kind, metric, value, threshold, "
            f"message, recommended_action, status, created_at FROM alerts{where} "
            f"ORDER BY created_at DESC", params
        ).fetchall()
        return [AlertRecord(*r) for r in rows]

    _COUNT_BY_ALLOWED = frozenset({
        ("experiments", "research_state"), ("experiments", "kind"),
        ("strategies", "deployment_state"), ("strategies", "research_state"),
        ("alerts", "status"),
    })

    def count_by(self, table: str, column: str) -> dict[str, int]:
        """Grouped row counts, e.g. count_by('experiments','research_state'). Only a
        fixed (table, column) allowlist is permitted (no arbitrary SQL)."""
        if (table, column) not in self._COUNT_BY_ALLOWED:
            raise ValueError(f"count_by not allowed for ({table}, {column})")
        rows = self.con.execute(f"SELECT {column}, COUNT(*) FROM {table} GROUP BY {column}").fetchall()
        return {r[0]: int(r[1]) for r in rows}

    def list_portfolio_models(self, *, strategy_id: str | None = None) -> list[PortfolioModelRecord]:
        clause = " WHERE strategy_id = ?" if strategy_id else ""
        params = [strategy_id] if strategy_id else []
        ids = [r[0] for r in self.con.execute(
            f"SELECT portfolio_id FROM portfolio_models{clause}", params).fetchall()]
        return [m for pid in ids if (m := self.get_portfolio_model(pid)) is not None]

    def list_benchmarks(self) -> list[BenchmarkRecord]:
        rows = self.con.execute("SELECT * FROM benchmarks").fetchall()
        return [BenchmarkRecord(*r) for r in rows]

    def list_cost_models(self) -> list[CostModelRecord]:
        rows = self.con.execute("SELECT * FROM cost_models").fetchall()
        return [CostModelRecord(*r) for r in rows]

    def row_count(self, table: str) -> int:
        if table not in {"strategies", "features", "datasets", "experiments", "artifacts",
                         "transitions", "alerts", "portfolio_models", "benchmarks", "cost_models"}:
            raise ValueError(f"unknown table: {table}")
        row = self.con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        assert row is not None
        return int(row[0])

    # ---- transitions (the "why" audit trail) ----

    def transition(
        self, *, entity_type: str, entity_id: str, axis: str, to_state: str,
        reason: str, actor: str | None = None,
    ) -> TransitionRecord:
        """Move an entity to a new lifecycle state, recording from/to/**reason**.

        ``axis`` is 'research' or 'deployment'. Validates ``to_state`` against the
        axis's allowed set, reads the current state (the ``from_state``), writes a
        ``transitions`` row, and updates the entity's state column. Returns the
        recorded transition."""
        valid = RESEARCH_STATES if axis == "research" else DEPLOYMENT_STATES if axis == "deployment" else None
        if valid is None:
            raise ValueError(f"axis must be 'research' or 'deployment', got {axis!r}")
        if to_state not in valid:
            raise ValueError(f"{to_state!r} is not a valid {axis} state ({sorted(valid)})")

        col = "research_state" if axis == "research" else "deployment_state"
        table = "strategies" if entity_type == "strategy" else "experiments" if entity_type == "experiment" else None
        if table is None:
            raise ValueError(f"unknown entity_type {entity_type!r}")
        if table == "experiments" and axis == "deployment":
            raise ValueError("experiments have no deployment_state; only strategies do")
        id_col = f"{entity_type}_id"
        cur = self.con.execute(
            f"SELECT {col} FROM {table} WHERE {id_col} = ?", [entity_id]
        ).fetchone()
        if cur is None:
            raise ValueError(f"{entity_type} {entity_id} not found")
        from_state = cur[0]

        tr = TransitionRecord(
            transition_id=_new_id("trans"), entity_type=entity_type, entity_id=entity_id,
            axis=axis, from_state=from_state, to_state=to_state, reason=reason,
            transitioned_at=_now(), actor=actor,
        )
        self.con.execute(
            "INSERT INTO transitions VALUES (?,?,?,?,?,?,?,?,?)",
            [tr.transition_id, tr.entity_type, tr.entity_id, tr.axis, tr.from_state,
             tr.to_state, tr.reason, tr.transitioned_at, tr.actor],
        )
        self.con.execute(f"UPDATE {table} SET {col} = ? WHERE {id_col} = ?", [to_state, entity_id])
        return tr

    def transitions_for(self, entity_id: str) -> list[TransitionRecord]:
        rows = self.con.execute(
            "SELECT transition_id, entity_type, entity_id, axis, from_state, to_state, reason, "
            "transitioned_at, actor FROM transitions WHERE entity_id = ? ORDER BY transitioned_at", [entity_id]
        ).fetchall()
        return [TransitionRecord(*r) for r in rows]

    # ---- dependency graph (the FK chain) ----

    def dependencies(self, experiment_id: str) -> dict[str, Any]:
        """Resolve an experiment's dependency chain: its strategy, dataset, feature
        ids, and produced artifacts. Walks the foreign-key edges — the graph is the
        FKs, not a separate structure."""
        exp = self.get_experiment(experiment_id)
        if exp is None:
            raise ValueError(f"experiment {experiment_id} not found")
        artifacts = [
            r[0] for r in self.con.execute(
                "SELECT artifact_id FROM artifacts WHERE experiment_id = ?", [experiment_id]
            ).fetchall()
        ]
        return {
            "experiment_id": experiment_id,
            "parent_experiment_id": exp.parent_experiment_id,
            "strategy_id": exp.strategy_id,
            "dataset_id": exp.dataset_id,
            "feature_ids": exp.feature_ids,
            "artifact_ids": artifacts,
        }
