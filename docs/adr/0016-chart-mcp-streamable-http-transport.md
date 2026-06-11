# ADR 0016 — Chart-data MCP on Streamable HTTP transport

| Field | Value |
|---|---|
| Date | 2026-06-10 (accepted 2026-06-11 after live verification) |
| Status | Accepted |
| Phase | P3 (agent tool dispatch); cross-phase for any non-localhost agent deployment |
| Supersedes | — |
| Related | 0002 (single OrderRouter — the MCP is read-only and never submits orders), 0006 v2 (LLM gating — the agent is the only LLM consumer of this MCP), 0010 (agent separate process, MCP reads / API writes — draft) |

## Context

The P3 agent (`/agent`) lets the model call read-only workbench tools — `get_account_state`, `list_strategies`, `list_recent_signals`, market data — served by the chart-data MCP (`apps/mcp-server`, port 8765). The backend hands Anthropic an `mcp_servers` connector block (`app/llm/anthropic_client.py`, beta `mcp-client-2025-04-04`) and **Anthropic's servers dispatch the tool calls** from their side; the URL comes from `AGENT_MCP_SERVER_URL` (`app/config.py`, default `http://127.0.0.1:8765`).

Tool dispatch has never been verified end-to-end. The standing explanation was "Anthropic's servers can't reach `127.0.0.1`, so every tool turn 400s — needs a tunnel." A cloudflared tunnel test on 2026-06-10 **disproved that as the root cause**: with `:8765` exposed at a public `trycloudflare.com` URL, Anthropic's servers *did* reach the MCP (confirmed in the tunnel access log — inbound requests to `/sse`, origin `127.0.0.1:8765`), yet the turn still failed with `400 invalid_request_error: "Connection error while communicating with MCP server."` The tunnel log showed Anthropic open the `/sse` stream and immediately **cancel it** (`stream canceled by remote with error code 0`).

The cause is a transport mismatch. The chart-MCP runs FastMCP's **legacy SSE transport** (`server.run(transport="sse")`, `apps/mcp-server/src/workbench_mcp/server.py`). Anthropic's `mcp-client-2025-04-04` url-connector speaks **Streamable HTTP** to remote MCP servers; it cannot complete a handshake against the older SSE transport. So reachability was necessary but not sufficient — `p3-complete` is blocked on the transport, not on a tunnel.

## Decision

Switch the chart-data MCP (`apps/mcp-server`, port 8765) from FastMCP's `sse` transport to **`streamable-http`** (served at `/mcp`). Point the agent connector default at the `/mcp` path (`AGENT_MCP_SERVER_URL` default `http://127.0.0.1:8765/mcp`; `runtime.py` default likewise). The transport change is the only mechanism by which Anthropic's server-side connector can complete a tool-call handshake.

This decision covers **only** the chart-data MCP on 8765. The workbench-state MCP on 8766 (`apps/mcp-workbench`) keeps its SSE transport — its sole consumer is the `apps/agent` process via the Python MCP SDK's `sse_client`, which speaks SSE natively and is unaffected.

## Rationale

- **The chart-MCP's only consumer is Anthropic's connector.** Verified: `apps/agent` connects to the workbench-MCP on **8766** (`WORKBENCH_MCP_BASE`, default `http://127.0.0.1:8766`), not 8765. The backend never opens a client-side MCP connection to 8765 — it passes the URL to Anthropic and Anthropic dispatches. So changing 8765's transport has exactly one affected client, and that client *requires* the new transport. There is no consumer to break.
- **FastMCP supports it natively.** `mcp` 1.27.1 — `FastMCP.run(transport="streamable-http")` is a one-line change; the server mounts the streamable-HTTP app at `/mcp`. No custom transport code.
- **Streamable HTTP is the forward transport for remote MCP.** The MCP ecosystem (and Anthropic's connector) moved from the dual-endpoint SSE transport (`GET /sse` event stream + `POST /messages`) to single-endpoint Streamable HTTP. For any eventual non-localhost product deployment, Streamable HTTP is the transport Anthropic's connector expects regardless of tunnels.
- **Empirical evidence, not speculation.** The tunnel test produced the exact failure signature (Anthropic reaches the server, opens `/sse`, cancels) that a transport mismatch predicts. The previous "localhost unreachable" hypothesis was falsified by the same test.

Trade-off accepted: this change cannot be fully verified until the new transport is re-tested through a tunnel (the dev box's intermittent Norton SSL inspection blocks reliable Anthropic egress, and Anthropic can only reach a publicly-exposed URL). The change is the necessary precondition; the confirming re-test + `p3-complete` tag follow once a stable Norton-off window + tunnel are available.

## Implementation notes

- `apps/mcp-server/src/workbench_mcp/server.py`: `server.run(transport="sse")` → `server.run(transport="streamable-http")`. FastMCP serves the MCP endpoint at `/mcp`.
- `apps/backend/app/config.py`: `agent_mcp_server_url` default `http://127.0.0.1:8765` → `http://127.0.0.1:8765/mcp`; update the comment to name the transport + the `/mcp` path. Empty string still disables the connector (pure-chat agent) for local dev without a tunnel.
- `apps/backend/app/llm/runtime.py`: the `mcp_server_url` default likewise gains `/mcp`.
- Docker healthcheck (`apps/mcp-server/Dockerfile`, `docker-compose.yml`) is a TCP socket connect to 8765 — transport-agnostic, no change.
- Stale doc comments that describe 8765 as SSE (`apps/mcp-workbench/src/mcp_workbench/server.py`, `config.py`) updated for accuracy.
- No CI invariant changes. The MCP read-only invariant (`check_mcp_readonly`) constrains *what tools do* (no order submission), not the transport; it is unaffected.
- To verify after deploy: expose `:8765` via a tunnel, set `AGENT_MCP_SERVER_URL=https://<tunnel>/mcp`, recreate the backend (`docker compose up -d --force-recreate backend` — `restart` does not re-read `.env`), and drive a tool-using B2 turn; expect `mcp_tool_use` / `mcp_tool_result` blocks instead of the 400.

## Consequences

- **Positive**: removes the transport blocker on P3 tool dispatch; aligns the chart-MCP with the transport Anthropic's connector and the broader MCP ecosystem expect; unblocks the eventual public/non-localhost agent deployment.
- **Negative**: the chart-MCP no longer serves the SSE endpoint on 8765. Any *future* client written against `GET /sse` on 8765 would have to use the streamable-HTTP client instead (today there is none). The change ships **unverified against live Anthropic** until the tunnel re-test, so it carries a "should work, not yet proven end-to-end" caveat until `p3-complete` is tagged.
- **Neutral**: the served URL path moves from `/sse` to `/mcp`; the bare `:8765` default gains a path segment. Tool semantics, auth posture (none today — see triggers), and read-only behavior are unchanged.

## Verification (2026-06-11)

Re-tested through a cloudflared tunnel during a stable Norton-off window, per the procedure in the implementation notes. With the chart-MCP rebuilt on `streamable-http` (serving `/mcp`), `AGENT_MCP_SERVER_URL` pointed at `https://<tunnel>/mcp`, and the backend recreated, a B2 turn (session #10, `claude-haiku-4-5`) produced a real **`mcp_tool_use` → `mcp_tool_result`** round-trip: Anthropic's connector dispatched `get_account_state` to the chart-MCP and a structured result returned. This satisfies the verification criterion in the implementation notes (tool-dispatch blocks instead of the prior `400`), so the transport decision is **Accepted**.

The round-trip also surfaced a **separate, pre-existing bug** unrelated to the transport: the chart-MCP's user-scoped read tools called the backend without any auth the backend recognizes (`get_account` et al. sent no bearer; the `X-Workbench-Auth` shared secret is honored only by `/internal/ping`), so the dispatched tool returned `401`. That gap was masked until this transport fix let tools dispatch at all. It is fixed separately by reusing the `WORKBENCH_MCP_KEY` bearer token for the chart-MCP's backend reads (see `docs/runbook/credentials.md` §2a); `p3-complete` is tagged only after a tool returns real data end-to-end.

## Alternatives considered (not chosen)

- **Keep SSE, find a URL/config tweak.** Rejected: the failure is a transport-level handshake mismatch, not a path mismatch — the tunnel test showed Anthropic cancel the SSE stream after opening it. No `AGENT_MCP_SERVER_URL` shape makes the legacy SSE transport speak Streamable HTTP. Reconsider only if Anthropic's connector adds SSE support.
- **Drop server-side dispatch; have the agent call MCP client-side** (the `apps/agent` pattern, ADR 0010 draft). A larger architectural move that would make the transport question moot for the agent by calling tools locally (no public exposure, no Anthropic reachability). Deferred: it re-architects the P3 `/agent` path and is out of scope for unblocking the existing server-side path. If ADR 0010's client-side architecture supersedes server-side dispatch for `/agent`, this ADR's relevance narrows to any remaining server-side connector use.
- **Run both transports** (SSE on 8765, Streamable HTTP on another port). Rejected: needless complexity for a server with a single consumer that needs only the new transport.

## Re-evaluation triggers

- The tunnel re-test does **not** produce `mcp_tool_use` blocks (i.e. Streamable HTTP also fails to handshake) — revisit the connector/transport assumptions before tagging `p3-complete`.
- The `/agent` path migrates to client-side MCP dispatch (ADR 0010 accepted + implemented) — this ADR's server-side rationale narrows or is superseded.
- The chart-MCP gains a non-Anthropic consumer, or the MCP is exposed to the public internet as a standing deployment — at that point add authentication to the connector (the `mcp_servers` block supports an authorization token; today the server is unauthenticated and was only ever localhost-bound), which would warrant its own ADR.
