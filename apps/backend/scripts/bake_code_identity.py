"""Write `/app/BUILD_CODE_IDENTITY.json` at IMAGE BUILD time, derived from the copied tree.

Run once from the Dockerfile, immediately after `COPY app ./app`. The value is **derived from the bytes
that were just copied**, not passed in: there is no build ARG and no environment variable, so nothing an
operator supplies at container creation can influence what the image claims about itself.

The startup gate (`verify_runtime_code_identity.py`) re-derives the same value at boot and refuses on
mismatch. That pair catches code edited into a running container, a bind mount shadowing `/app/app`, and
a partially-copied image — none of which any declaration-based check can see.

⛔ It does NOT prove the right image was deployed; a wrong image describes itself correctly. That is the
host-side attestation's job (MDQ preflight Gate 6).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.validation.deployment_identity import (  # noqa: E402
    CODE_DIGEST_SCHEMA,
    derive_runtime_code_digest,
)

IDENTITY_PATH = Path("/app/BUILD_CODE_IDENTITY.json")
CODE_ROOT = Path("/app/app")


def main() -> int:
    digest = derive_runtime_code_digest(CODE_ROOT)
    IDENTITY_PATH.write_text(
        json.dumps({"schema": CODE_DIGEST_SCHEMA, "code_digest": digest,
                    "measured_root": str(CODE_ROOT)}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(f"baked code identity {digest} -> {IDENTITY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
