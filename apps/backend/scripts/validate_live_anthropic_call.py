"""Validate a REAL Anthropic call (P6 §1b.12 Anthropic half) end to end.

Item 2 of ``docs/runbook/live-verification.md`` requires a real streamed agent
turn that records a non-zero ``total_cost_usd``. The browser/SSE half of that
(the ``/agent`` chat streaming tokens to the UI) still needs the stack up, but
the *Anthropic-call* half can be proven standalone: this script drives the same
production code paths the runtime uses --- ``app.llm.create_message`` (the
non-streaming call the runtime issues, runtime.py) and ``app.llm.stream_message``
(the streaming surface) --- against the real ``ANTHROPIC_API_KEY`` loaded from
``.env``, then runs the real ``estimate_cost`` pricing path and asserts the cost
is non-zero. It places NO orders, needs no browser, and needs no stack.

Run it from the host backend venv (or inside the backend container) on a
non-Norton network with a real key configured:

    .venv/Scripts/python.exe scripts/validate_live_anthropic_call.py

It spends a tiny amount of real Anthropic credit (a few hundred Haiku tokens,
well under one cent). Exit code is non-zero if any HARD check fails, so it can
gate a sign-off. The model defaults to the configured ``AGENT_DEFAULT_MODEL``.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make ``app`` importable whether launched from apps/backend, the repo root, or
# via a full path (sys.path[0] is the script dir, not apps/backend).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.llm.anthropic_client import (  # noqa: E402
    AnthropicClientNotConfigured,
    create_message,
    stream_message,
)
from app.llm.pricing import PRICING_TABLE, estimate_cost  # noqa: E402

# A deliberately tiny prompt: cheap, deterministic-ish, and easy to eyeball.
_SYSTEM = "You are a terse assistant. Answer in one short sentence."
_USER = "In one sentence, what is a stop-loss order in trading?"
_MAX_TOKENS = 128


async def _run_non_streaming(api_key: str, model: str) -> tuple[int, int, str]:
    """Issue the runtime's actual call. Returns (in_tokens, out_tokens, text)."""
    call = await create_message(
        api_key=api_key,
        model=model,
        system=_SYSTEM,
        messages=[{"role": "user", "content": _USER}],
        max_tokens=_MAX_TOKENS,
    )
    text = " ".join(
        b.get("text", "") for b in call.content_blocks if b.get("type") == "text"
    ).strip()
    return call.input_tokens, call.output_tokens, text


async def _run_streaming(api_key: str, model: str) -> tuple[int, int, str, bool]:
    """Drive the streaming surface. Returns (in, out, text, saw_stop)."""
    in_tokens = 0
    out_tokens = 0
    chunks: list[str] = []
    saw_stop = False
    async for ev in stream_message(
        api_key=api_key,
        model=model,
        system=_SYSTEM,
        messages=[{"role": "user", "content": _USER}],
        max_tokens=_MAX_TOKENS,
    ):
        etype = ev.get("type")
        raw = ev.get("raw")
        if etype == "message_start":
            usage = getattr(getattr(raw, "message", None), "usage", None)
            in_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        elif etype == "content_block_delta":
            delta = getattr(raw, "delta", None)
            text = getattr(delta, "text", None)
            if text:
                chunks.append(text)
        elif etype == "message_delta":
            usage = getattr(raw, "usage", None)
            if usage is not None:
                out_tokens = int(getattr(usage, "output_tokens", out_tokens) or out_tokens)
        elif etype == "message_stop":
            saw_stop = True
    return in_tokens, out_tokens, "".join(chunks).strip(), saw_stop


def _report(passed: list[str], failed: list[str]) -> None:
    for c in passed:
        print(f"    PASS  {c}")
    for c in failed:
        print(f"    FAIL  {c}")


async def _validate() -> int:
    settings = get_settings()
    api_key = settings.anthropic_api_key
    api_key = api_key.get_secret_value() if hasattr(api_key, "get_secret_value") else api_key
    model = settings.agent_default_model

    print(f"model={model}  key_len={len(api_key) if api_key else 0}  "
          f"in_pricing_table={model in PRICING_TABLE}")

    if not api_key:
        print("  FAIL  ANTHROPIC_API_KEY is empty - set it in .env")
        return 1

    passed: list[str] = []
    failed: list[str] = []

    def hard(name: str, ok: bool) -> None:
        (passed if ok else failed).append(name)

    # --- Non-streaming (the runtime's create_message path) ---
    print("\n=== non-streaming create_message ===")
    try:
        n_in, n_out, n_text = await _run_non_streaming(api_key, model)
    except AnthropicClientNotConfigured as exc:
        print(f"  FAIL  client not configured: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001 - report any live failure plainly
        print(f"  CALL FAILED: {type(exc).__name__}: {exc}")
        return 1
    print(f"  in_tokens={n_in} out_tokens={n_out}")
    print(f"  text: {n_text[:200]}")
    n_cost = estimate_cost(model, n_in, n_out)
    print(f"  estimate_cost=${n_cost}")
    hard("non-streaming input_tokens > 0", n_in > 0)
    hard("non-streaming output_tokens > 0", n_out > 0)
    hard("non-streaming returned text", bool(n_text))
    hard("non-streaming estimate_cost > 0 (total_cost_usd would be non-zero)", n_cost > 0)

    # --- Streaming (the SSE-backing stream_message surface) ---
    print("\n=== streaming stream_message ===")
    try:
        s_in, s_out, s_text, saw_stop = await _run_streaming(api_key, model)
    except Exception as exc:  # noqa: BLE001 - report any live failure plainly
        print(f"  STREAM FAILED: {type(exc).__name__}: {exc}")
        return 1
    print(f"  in_tokens={s_in} out_tokens={s_out} saw_message_stop={saw_stop}")
    print(f"  text: {s_text[:200]}")
    s_cost = estimate_cost(model, s_in, s_out)
    print(f"  estimate_cost=${s_cost}")
    hard("streaming yielded text deltas", bool(s_text))
    hard("streaming saw message_stop", saw_stop)
    hard("streaming input_tokens > 0", s_in > 0)
    hard("streaming output_tokens > 0", s_out > 0)
    hard("streaming estimate_cost > 0", s_cost > 0)

    print("\n--- checks ---")
    _report(passed, failed)
    ok = not failed
    print("\n" + ("RESULT: PASS - real Anthropic call + non-zero cost confirmed"
                  if ok else "RESULT: FAIL (see above)"))
    return 0 if ok else 1


def main() -> None:
    sys.exit(asyncio.run(_validate()))


if __name__ == "__main__":
    main()
