"""P6b §4 eval-harness package (ADR 0006 v2).

ALLOWLIST NOTE: this directory is in ``ALLOWED_DIRS`` of
``check_no_llm_in_order_path.sh`` (ADR 0006 v2 §2). ``gate.py`` calls Anthropic
to decide Mode B's act/skip on PAPER signals; the directory is distinct from
``app/llm/`` so the LLM-in-paper-path boundary is visible in code review. The
LLM never reaches a live broker here — Mode B routes through ``OrderRouter.submit``
with a paper-only source (ADR 0002 intact); the live opt-in bypass is §5.
"""
