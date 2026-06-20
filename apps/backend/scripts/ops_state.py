"""P11 §1 — print the operational FEATURE REGISTRY (static catalog).

The no-UI operator surface for "what operational features exist, how to turn each on, and
its promotion verdict." This is the **static** registry (key / kind / ADR / flag /
verified / note) — it needs no running server and no auth.

For the **live** enabled/healthy state (which strategies have a flag on right now), query
the running server: ``GET /api/v1/ops/state`` (it reads the live strategy engine). A
standalone script can't see the server's in-memory engine, and the API is auth-gated, so
this CLI deliberately shows only the static catalog. ASCII-only output (Windows cp1252).

    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe apps/backend/scripts/ops_state.py
"""
from __future__ import annotations

from app.ops.feature_registry import FEATURES


def main() -> int:
    hdr = f"{'key':20s} {'category':14s} {'kind':10s} {'flag':28s} {'verified':10s} {'ADR':14s}"
    print("Operational feature registry (static). Live enabled/healthy: GET /api/v1/ops/state")
    print(hdr)
    print("-" * len(hdr))
    for f in FEATURES:
        print(f"{f.key:20s} {f.category:14s} {f.kind:10s} {str(f.enable_flag or '(infra)'):28s} "
              f"{f.verified:10s} {f.governing_adr:14s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
