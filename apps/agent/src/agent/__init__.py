"""apps/agent — the P6 stateless proposal-generation agent.

Reads workbench state via workbench-mcp (SSE), writes proposals via the
backend HTTP API. Per the Decisions doc: stateless, single-shot, no DB access.

Session 1a ships infrastructure only. Session 1b wires the invocation path.
"""

__version__ = "0.1.0"
