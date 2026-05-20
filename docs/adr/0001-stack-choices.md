# ADR 0001 — Stack choices

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-05-20 |
| Phase | P0 |
| Supersedes | — |

## Context

The Trading Workbench is a single-trader local-first app. Decisions taken here become hard to reverse once code starts depending on them.

## Decision

| Concern | Choice |
|---|---|
| Backend | **FastAPI** (Python 3.12) |
| ORM + migrations | **SQLAlchemy 2.x** (async) + **Alembic** |
| Database | **SQLite** in P0; Postgres-ready via SQLAlchemy generics |
| Realtime | **WebSockets** (server-pushed) + in-process async event bus |
| Frontend | **React 19 + Vite 6 + TypeScript + Tailwind 3** |
| Broker SDK | **`alpaca-py`** (official) |
| Agent integration | **Claude Code** in IDE for dev; **server-side Anthropic SDK + MCP** for runtime (P6) |
| MCP exposure | **Separate process** (`apps/mcp-server/`) calling backend over HTTP |
| Packaging | **`pip` + venv** (Python); **`pnpm`** (Node); **Docker Compose** for one-command bring-up |
| Hosting | Local-first (everything bound to `127.0.0.1`); future hosted via Cloudflare Tunnel |

## Why these vs the alternatives

### Backend: FastAPI over Django / Flask / Node
- Native async means WebSockets, broker streaming, and strategy ticks share one event loop cleanly.
- Pydantic v2 gives us typed request/response models for free, which the strategy engine and risk gates will lean on heavily.
- Matches Jay's existing ComplyGen Lab stack — operational muscle memory transfers.

### Database: SQLite for MVP
- One file, no daemon, trivial backup.
- Adequate for a single trader's order/fill/journal volume by orders of magnitude.
- The async SQLAlchemy + `aiosqlite` driver supports the same query patterns we'd write against Postgres, so migrating later is config + `alembic upgrade head`, not a rewrite.
- The only thing we can't do on SQLite is multi-process concurrent writes. When that becomes a constraint (P6+ multi-strategy autonomous mode), Postgres lands.

### Frontend: React + Vite over Next.js / Remix
- The workbench is a single-page app on `127.0.0.1`. SSR doesn't earn its complexity for a local trader UI.
- Vite's dev server is fast and the build output is plain static files.
- TanStack Query for server state, Zustand for UI state — both small, both well-understood.

### MCP server as a *separate process* (not a backend module)
- The MCP server is a tool surface for an LLM. Coupling it to the backend's import graph would let an agent-mediated bug (tool call → exception → backend crash) take down the trader's manual UI session too.
- Separate process = a separate failure domain. Backend stays up if MCP crashes.
- The boundary is enforced by a shared-secret HTTP header (`X-Workbench-Auth: $MCP_BACKEND_TOKEN`) on internal endpoints — same primitive whether MCP is local or split across a network later.
- See ADR 0002 for the related order-routing invariant the MCP server must respect.

### Agent layer: dev-time vs runtime are *different things*
- **Dev-time:** Claude Code in the IDE invokes MCP tools to explore strategies, read positions, etc. It authenticates itself; the workbench doesn't carry an Anthropic key.
- **Runtime:** From P6, the backend's strategy engine calls `api.anthropic.com` directly (using `ANTHROPIC_API_KEY` from `.env`) with the workbench MCP server attached as tools. The user isn't at the IDE when this fires.
- Same MCP tool surface, different invocation context, different security posture. Worth being explicit so we don't accidentally collapse the two.

### Packaging: pip+venv over uv
- The P0 checklist recommended `uv`. Jay overrode this in favor of `pip + venv`.
- Reason on file: zero net-new tooling to install; pip is what's already on the machine.
- Cost: pip is slower than uv on cold installs (~30s vs ~3s). Acceptable.
- If install time starts dominating (e.g., CI spending minutes on dep resolution), revisit.

## Consequences

- **Good:** every component is replaceable. SQLite → Postgres, Vite → Next, FastAPI → something else — each is a contained migration because the boundaries are HTTP/SQL, not in-process imports.
- **Good:** the single-process-per-service model is debuggable. Three processes, three sets of logs, no orchestrator-layer mysteries in P0.
- **Bad:** running everything on `127.0.0.1` means we can't share an instance across multiple traders. That's intentional (Non-Goal NG1) but worth restating — when multi-user lands, auth + isolation are not retrofits we want to discover late.
- **Bad:** SQLite's single-writer constraint will bite us in P6+ when multiple Agent Strategies tick concurrently. The mitigation is documented (move to Postgres); not addressed in P0.

## References

- Design Doc §11 (Technology Stack)
- Design Doc §4 (High-Level Architecture)
- P0 Session 1 v0.1 §0.1 (locked tooling decisions)
- ADR 0002 (Single order entry point)
