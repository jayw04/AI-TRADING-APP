"""Artifact store + registry access for MKT-PROJ-001 models (design §17.4, NFR-002).

``save_artifact`` dumps a trained ``TrainedModels`` bundle with joblib, hashes
it (sha256), and returns the registry-row fields; the research script persists
the row. Loading verifies the hash before unpickling — a tampered or corrupted
artifact refuses to load rather than silently projecting garbage.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

from app.services.market_projection.schemas import FEATURE_VERSION, LABEL_VERSION

DEFAULT_ARTIFACT_DIR = "data/market_projection/models"


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def save_artifact(
    models: Any,
    *,
    projection_type: str,
    model_type: str,
    training_window: str,
    validation_window: str,
    git_commit: str | None,
    artifact_dir: str = DEFAULT_ARTIFACT_DIR,
) -> dict[str, Any]:
    """Dump the bundle and return the registry-row field dict (status=candidate)."""
    import joblib

    os.makedirs(artifact_dir, exist_ok=True)
    version = f"{model_type}-{FEATURE_VERSION}-{training_window.replace('..', '_')}" + (
        f"-{git_commit}" if git_commit else ""
    )
    path = os.path.join(artifact_dir, f"{version}.joblib")
    joblib.dump(models, path)
    return {
        "model_version": version,
        "model_type": model_type,
        "projection_type": projection_type,
        "artifact_path": path,
        "artifact_hash": _sha256(path),
        "feature_version": FEATURE_VERSION,
        "label_version": LABEL_VERSION,
        "training_window": training_window,
        "validation_window": validation_window,
        "git_commit": git_commit,
        "status": "candidate",
    }


def load_artifact(artifact_path: str, expected_hash: str) -> Any:
    """Hash-verified load (refuses on mismatch)."""
    import joblib

    actual = _sha256(artifact_path)
    if actual != expected_hash:
        raise ValueError(
            f"artifact hash mismatch for {artifact_path}: expected {expected_hash[:12]}…, "
            f"got {actual[:12]}… — refusing to load"
        )
    return joblib.load(artifact_path)
