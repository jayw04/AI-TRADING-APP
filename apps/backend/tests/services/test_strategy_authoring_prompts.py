"""P7 §1 — the strategy-generation system prompts + output schema are well-formed
and self-consistent (esp. the indicator-vocabulary drift guard)."""
from __future__ import annotations

from app.indicators.computer import CORE_INDICATORS
from app.services.strategy_authoring import prompts


def test_version_and_model():
    assert prompts.GENERATION_PROMPT_VERSION  # set
    # Sonnet — Decision 6 (not Haiku, not Opus).
    assert prompts.GENERATION_MODEL == "claude-sonnet-4-6"
    assert "haiku" not in prompts.GENERATION_MODEL
    assert "opus" not in prompts.GENERATION_MODEL


def test_output_tool_schema_shape():
    tool = prompts.STRATEGY_OUTPUT_TOOL
    assert tool["name"] == "emit_strategy"
    schema = tool["input_schema"]
    assert schema["type"] == "object"
    assert set(schema["required"]) == {"code", "assumptions", "explanation"}
    assert schema["properties"]["code"]["type"] == "string"
    assert schema["properties"]["assumptions"]["type"] == "array"


def test_indicator_vocabulary_covers_every_engine_indicator():
    # Drift guard: a new indicator added to the engine without updating the prompt
    # fails here.
    for name in CORE_INDICATORS:
        assert name in prompts.INDICATOR_VOCABULARY, f"{name} missing from the prompt vocabulary"


def test_multi_output_subseries_documented():
    assert "macd, signal, hist" in prompts.INDICATOR_VOCABULARY
    assert "bb_lower, bb_mid, bb_upper" in prompts.INDICATOR_VOCABULARY


def test_generation_prompt_states_the_contract():
    p = prompts.GENERATION_SYSTEM
    # Interface essentials.
    for token in ("on_bar", "get_indicators", "submit_order", "params_schema", "Strategy"):
        assert token in p
    # Isolation + the unsupported-indicator policy + human-readability + tool-only.
    assert "Anthropic-SDK" in p  # the no-LLM-at-runtime isolation constraint
    assert "no broker" in p.lower()
    assert "MUST NOT implement a new indicator" in p
    assert "human-readable" in p.lower()
    assert "emit_strategy" in p
    # Single-shot: no clarifying questions.
    assert "do NOT ask clarifying questions" in p


def test_all_three_variants_present_and_tool_only():
    for p in (prompts.GENERATION_SYSTEM, prompts.REVISION_SYSTEM, prompts.DEBUG_SYSTEM):
        assert p.strip()
        assert "emit_strategy" in p
        assert prompts.INDICATOR_VOCABULARY in p  # each carries the vocabulary


def test_revision_returns_complete_file_not_diff():
    assert "COMPLETE revised file (not a diff)" in prompts.REVISION_SYSTEM


def test_render_helpers_inject_inputs():
    assert "buy low sell high" in prompts.build_generation_user_message("buy low sell high")
    rev = prompts.build_revision_user_message("class X: pass", "tighten the stop")
    assert "class X: pass" in rev and "tighten the stop" in rev
    dbg = prompts.build_debug_user_message("bad code", "SyntaxError: bad")
    assert "bad code" in dbg and "SyntaxError: bad" in dbg
