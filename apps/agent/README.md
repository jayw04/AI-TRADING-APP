# agent — Trading Workbench P6 proposal-generation agent

Stateless, single-shot proposal-generation agent (P6). Per the
[P6 Architectural Decisions](../../Docs/implementation/TradingWorkbench_P6_Architectural_Decisions_v0_1.md):

- **Stateless, single-shot** (Decision 1): each invocation reads its full context,
  produces one proposal, persists it, and exits. No in-memory state across runs.
- **Reads via workbench-mcp SSE; writes via the backend HTTP API** (Decision 2).
  The agent **never touches the database directly** — enforced by the CI invariant
  `check_agent_no_db_access.sh` (the 13th invariant).
- **Hard pre-call cost cap** (Decision 6): every LLM call goes through
  `agent.llm_call.call_with_budget`, which checks the backend budget endpoint
  *before* invoking Anthropic and drops the proposal if rejected.

## Session 1a scope

Infrastructure only. This package ships:

- `agent.config` — env-var configuration (`AGENT_API_KEY`, `BACKEND_API_BASE`,
  `WORKBENCH_MCP_BASE`, `ANTHROPIC_API_KEY`).
- `agent.budget` — the pre-call budget client + conservative cost estimator.
- `agent.llm_call` — the single LLM-call wrapper (budget check → Anthropic →
  typed failure), unit-tested with mocks.

There is **no invocation path yet** — `python -m agent` prints a stub message.
Session 1b wires the proposal-generation loop, the MCP read tools, and the
frontend.

## Local dev

```bash
cd apps/agent
pip install -e ".[dev]"
pytest          # unit tests only; no real Anthropic calls in 1a
ruff check .
mypy src
```
