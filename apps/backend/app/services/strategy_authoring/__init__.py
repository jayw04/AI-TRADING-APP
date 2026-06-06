"""NL → Python strategy authoring (P7).

§1 ships the version-controlled system prompts + the structured output schema
that drive generation; §2+ add the generation service, backtest integration, and
the refinement loop. Generated strategies are DETERMINISTIC at runtime (the LLM
is used in authoring, not execution), enter the standard backtest → paper →
activation lifecycle, and obey strategy isolation — so this package does not
touch the order path and the existing CI invariants cover the generated code.
"""
