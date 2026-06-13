# ADR 0017 — OS trust store for outbound TLS verification

| Field | Value |
|---|---|
| Date | 2026-06-12 |
| Status | Accepted |
| Phase | Cross-phase (affects all outbound HTTPS: Alpaca, Anthropic) |
| Supersedes | — |
| Related | 0003 (Fernet credential encryption — the other half of the broker-connection trust story) |

## Context

The platform's two external dependencies — Alpaca (execution + market data) and
Anthropic (LLM assistance) — are reached over HTTPS. The `alpaca-py` SDK and the
`anthropic` SDK, and the `requests`/`httpx`/`urllib3` clients beneath them, verify
server certificates against the **`certifi`** CA bundle: a fixed Mozilla root set
shipped as a Python package, independent of the operating system's trust store.

On the primary development machine (Windows + Norton), Norton's
"encrypted-connection scanning" performs TLS inspection: it MITMs outbound HTTPS
and presents a certificate signed by a **"Norton Web/Mail Shield"** root. Norton
installs that root into the **Windows system trust store** (which is why browsers
and other OS-trust clients accept it), but it is **not** in `certifi`. The result
is `CERTIFICATE_VERIFY_FAILED` on every Alpaca/Anthropic call — bar fetches,
fixture generation, and broker-enabled backend boot all fail — while the same
host's browsers work normally.

This has been a recurring, expensive blocker. The only known mitigation was
**disabling Norton's SSL scanning** for the session — a manual, security-reducing
toggle on a money application, easy to forget to re-enable, and intermittent
(Norton re-engages on its own). Pointing `REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE` /
`verify=certifi.where()` at certifi-style bundles never worked, because every such
bundle lacks Norton's root. A sibling app (`claude-trading-view`) reaches the same
Alpaca endpoints with no toggling — because it uses stdlib `urllib` with the
default SSL context, which verifies against the **OS trust store** and therefore
trusts Norton's root. The question: should this platform verify outbound TLS
against the OS trust store rather than certifi?

## Decision

Outbound TLS certificate verification is routed through the **operating-system
trust store** via the `truststore` package. A single idempotent helper —
`app/utils/tls_trust.py::enable_os_trust_store()` — calls
`truststore.inject_into_ssl()` once, as early as possible, so that
`requests`/`httpx`/`urllib` (and thus `alpaca-py` and `anthropic`) defer
certificate verification to the OS store instead of certifi.

It is invoked at two points:
1. **App startup** — first thing in `create_app()` (`app/main.py`), before any
   broker connect / market-data / Anthropic call.
2. **The bar-fetch path** — inside `BarCache._alpaca_fetch_bars`, so standalone
   callers that bypass app startup (backtest fetch scripts, fixture generation)
   are covered too.

The behavior is **on by default** and can be disabled with
`WORKBENCH_TLS_USE_OS_TRUST=0`.

## Rationale

The root cause is a **trust-store mismatch**, not anything about Alpaca, Python,
or the SDKs. The fix must change *which set of roots we trust*, and the only set
that contains the inspecting proxy's root is the OS store — the same store every
browser and the sibling `urllib` app already use successfully. `truststore` is the
modern, maintained, pure-Python way to make the stdlib `ssl` module (and everything
built on it) use that store; it is what pip itself uses for the same reason.

Alternatives and why they lose:

- **Disable Norton's SSL scanning (status quo).** Manual, intermittent, and
  *reduces* host security on a money app. It also only fixes the developer's box,
  not a general property of the software. Rejected as a workaround, not a fix.
- **Append Norton's root to certifi's `cacert.pem` / a custom `REQUESTS_CA_BUNDLE`.**
  Brittle (exporting the right DER, regenerating on certifi upgrades), host-specific
  (hard-codes one machine's proxy root into the repo or env), and a poor security
  posture (a committed extra root). Already tried; did not work cleanly.
- **Rewrite Alpaca access on stdlib `urllib`** like the sibling app. Throws away the
  maintained SDK (pagination, typed models, retry, the trading client) to gain only
  the OS-trust behavior `truststore` provides without a rewrite. Rejected.
- **`truststore`, on by default (chosen).** One dependency, one early call, no
  per-call-site change, no hard-coded roots. On hosts *without* an inspecting proxy
  it is effectively neutral — the OS store contains the same public roots certifi
  does — so it is safe to ship everywhere, not just the dev box.

Trade-off accepted: verification now depends on the host OS trust store being sane.
On a misconfigured or compromised OS store, that is a weaker guarantee than a pinned
Mozilla bundle — see Consequences. The opt-out env var preserves the certifi-only
path for any deployment that wants it.

## Implementation notes

- **Dependency:** `truststore>=0.9,<1.0` added to `apps/backend/pyproject.toml`
  (pure-Python, stdlib-only deps, requires Python ≥3.10; the backend is ≥3.11).
- **Helper:** `app/utils/tls_trust.py::enable_os_trust_store()` — idempotent
  (injects once via a module flag), never raises (a missing package or injection
  error logs `tls_os_trust_store_unavailable` and no-ops, so it cannot block
  startup), and honors `WORKBENCH_TLS_USE_OS_TRUST=0`.
- **Call sites:** `app/main.py` `create_app()` (earliest safe point — no HTTPS at
  import) and `app/market_data/bar_cache.py` `_alpaca_fetch_bars` (covers scripts).
- **Default / override:** enabled by default; set `WORKBENCH_TLS_USE_OS_TRUST=0`
  to fall back to certifi-only verification.
- **No CI invariant introduced.** `tls_trust.py` imports only `os`, `structlog`,
  and `truststore`; it does not touch the order path or the no-LLM allowlist.

## Consequences

- **Positive:** Alpaca and Anthropic HTTPS work on the Norton host **without
  disabling the inspector** — the toggle-Norton dance, the intermittent SSL flakes,
  and the "broker-enabled backend won't boot here" blocker are retired. Behavior is
  a property of the software, not a per-session manual step. CI/Linux is unaffected
  (its OS store carries the standard public roots).
- **Negative:** Certificate verification now trusts whatever the host OS trusts. A
  machine with a malicious/misconfigured root installed would be trusted where a
  pinned certifi bundle might not — i.e. we trade a fixed, auditable root set for the
  host's. On the dev box this is the *intended* behavior (we *want* to trust Norton's
  inspection); operators who want the stricter posture set
  `WORKBENCH_TLS_USE_OS_TRUST=0`. Also adds one dependency and one global `ssl`
  monkeypatch at process start.
- **Neutral:** The verification path moves from certifi to the OS store everywhere,
  including Anthropic calls; the set of trusted public roots is materially the same
  on a clean host.

## Alternatives considered (not chosen)

- **Disable Norton SSL scanning per session** — see Rationale. Reconsider never; it
  is a workaround, and this ADR exists to replace it.
- **Custom CA bundle with the proxy root appended** — see Rationale. Reconsider only
  if `truststore` stops being maintained or breaks on a target Python.
- **stdlib `urllib` rewrite of Alpaca access** — see Rationale. Reconsider only if we
  abandon `alpaca-py` for unrelated reasons.

## Re-evaluation triggers

- `truststore` becomes unmaintained, or fails to support a Python version the backend
  targets.
- A deployment requires a **pinned** root set for compliance/audit reasons — in which
  case default the env flag to off there and document the certifi-only posture.
- The host-trust assumption is ever judged too weak for a production (non-dev)
  deployment — revisit whether the inject should be gated to dev/Windows only rather
  than on-by-default everywhere.
