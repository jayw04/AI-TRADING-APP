"""Deployed-tree identity (R5c-2b) — prove the running code is the code that was reviewed.

A forward observation records `deployed_tree_identity`. If that value is simply whatever string the
caller passed, it evidences nothing: the record would say "this ran on commit X" because someone typed
X. This module derives the identity from the deployment itself and refuses when the evidence is absent
or disagrees.

## Three identities, kept distinct

  1. EMBEDDED BUILD COMMIT — stamped INTO the artifact at build time (`build_info.json` inside the
     image), with the working-tree cleanliness recorded at that moment;
  2. RUNNING ARTIFACT DIGEST — the image/artifact digest the runtime reports for what is executing;
  3. DEPLOYMENT MANIFEST — what the deploy step recorded it was deploying.

They are never collapsed into one string. Each is read from its own source, and the verifier requires
agreement among every identity the deployment model provides.

## Missing evidence is not mismatched evidence

`DeploymentEvidenceMissing` and `DeploymentEvidenceMismatch` are distinct stops, because they call for
different actions: the first means the deployment did not record what it ran (fix the deploy), the
second means the sources contradict each other (stop and investigate — something is running that was not
deployed). A dirty build tree is its own refusal: a commit is not an identity when uncommitted changes
were compiled into the artifact.

## A caller cannot supply the identity

Every input here is a PATH or an environment variable NAME. `expected_commit` may be pinned by the
operator, but it can only ever narrow the result — it is checked against the derived identity and never
substitutes for it.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.validation.forward_window import IntegrityStop

_HEX = frozenset("0123456789abcdef")


class DeploymentModel(StrEnum):
    """What evidence a deployment can be expected to produce."""
    CONTAINER = "CONTAINER"                  # build stamp + runtime digest + deploy manifest
    SOURCE_CHECKOUT = "SOURCE_CHECKOUT"      # build stamp + deploy manifest (no image digest)


REQUIRED_EVIDENCE: dict[DeploymentModel, tuple[str, ...]] = {
    DeploymentModel.CONTAINER: ("build_info", "runtime_digest", "deployment_manifest"),
    DeploymentModel.SOURCE_CHECKOUT: ("build_info", "deployment_manifest"),
}


class DeploymentIdentityError(IntegrityStop):
    """The running deployment could not be identified. Fails closed."""


class DeploymentEvidenceMissing(DeploymentIdentityError):
    """A source this deployment model requires produced nothing. The deployment did not record what it
    is running — distinct from sources that disagree."""


class DeploymentEvidenceMismatch(DeploymentIdentityError):
    """Two sources disagree, or the artifact was built from a dirty tree. Something is running that was
    not deployed as reviewed."""


@dataclass(frozen=True)
class DeploymentIdentityEvidence:
    """The three identities, kept separate, plus the agreed values and how they were established."""
    model: DeploymentModel
    embedded_build_commit: str | None
    embedded_build_tree_clean: bool | None
    embedded_build_digest: str | None          # the digest the build stamped, if it knew one
    build_info_source: str | None
    runtime_artifact_digest: str | None
    runtime_digest_source: str | None
    manifest_commit: str | None
    manifest_artifact_digest: str | None
    manifest_source: str | None
    agreed_commit: str
    agreed_artifact_digest: str | None
    identity_digest: str

    def to_open_provenance(self) -> dict[str, Any]:
        d = asdict(self)
        d["model"] = str(self.model)
        return d


def _is_commit(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 40 and set(text) <= _HEX


def _is_digest(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if text.startswith("sha256:"):
        text = text.split(":", 1)[1]
    return len(text) == 64 and set(text) <= _HEX


def _normalize_digest(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text.startswith("sha256:") else f"sha256:{text}"


def _read_json(path: Path, *, what: str) -> dict:
    if not path.is_file():
        raise DeploymentEvidenceMissing(f"{what} is absent at {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentEvidenceMissing(f"{what} at {path} is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise DeploymentEvidenceMissing(f"{what} at {path} is not an object")
    return payload


def verify_deployment_identity(
    *,
    model: DeploymentModel,
    build_info_path: Path | str,
    deployment_manifest_path: Path | str,
    runtime_digest_path: Path | str | None = None,
    runtime_digest_env: str | None = None,
    expected_commit: str | None = None,
) -> DeploymentIdentityEvidence:
    """Derive the running deployment's identity and refuse unless every available source agrees.

    `expected_commit` is an operator PIN: it can only narrow the result. It is compared against the
    derived identity and never becomes the identity.
    """
    required = REQUIRED_EVIDENCE[model]

    # (1) the build stamp inside the artifact
    build_path = Path(build_info_path)
    build = _read_json(build_path, what="the embedded build stamp")
    commit = str(build.get("commit", "")).strip().lower()
    if not _is_commit(commit):
        raise DeploymentEvidenceMissing(
            f"the embedded build stamp at {build_path} records no valid commit "
            f"({build.get('commit')!r})")
    # Cleanliness is load-bearing evidence, so it must be the JSON boolean itself. "false", "dirty",
    # 0 and 1 are all truthy-or-falsy in Python and none of them is a recorded fact.
    tree_clean = build.get("tree_clean")
    if tree_clean is False:
        raise DeploymentEvidenceMismatch(
            f"the artifact was built from a DIRTY working tree at {commit}; a commit does not identify "
            f"code that had uncommitted changes compiled into it")
    if tree_clean is not True:
        raise DeploymentEvidenceMissing(
            f"the embedded build stamp at {build_path} records tree_clean as {tree_clean!r}; it must be "
            f"the JSON boolean true or false")
    build_digest = build.get("image_digest")
    if build_digest is not None and not _is_digest(build_digest):
        raise DeploymentEvidenceMismatch(
            f"the embedded build stamp records an invalid artifact digest {build_digest!r}")

    # (2) what the runtime reports it is executing
    runtime_digest: str | None = None
    runtime_source: str | None = None
    if "runtime_digest" in required:
        runtime_path = Path(runtime_digest_path) if runtime_digest_path is not None else None
        if runtime_path is not None and runtime_path.exists():
            # A configured file that EXISTS is the evidence: a read failure is broken deployment
            # evidence, never a reason to quietly fall back to the environment.
            try:
                if not runtime_path.is_file():
                    raise DeploymentEvidenceMissing(
                        f"the runtime artifact digest at {runtime_path} is not a regular file")
                runtime_digest = runtime_path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise DeploymentEvidenceMissing(
                    f"the runtime artifact digest at {runtime_path} is unreadable: {exc}") from exc
            runtime_source = str(runtime_path)
        elif runtime_digest_env and os.environ.get(runtime_digest_env, "").strip():
            runtime_digest = os.environ[runtime_digest_env].strip()
            runtime_source = f"env:{runtime_digest_env}"
        else:
            raise DeploymentEvidenceMissing(
                f"the {model} deployment reports no running artifact digest (looked in "
                f"{runtime_digest_path!r} and env {runtime_digest_env!r}) — it cannot evidence what is "
                f"executing")
        if not _is_digest(runtime_digest):
            raise DeploymentEvidenceMismatch(
                f"the runtime-reported artifact digest {runtime_digest!r} is not a sha256 digest")

    # (3) what the deploy step recorded
    manifest_path = Path(deployment_manifest_path)
    manifest = _read_json(manifest_path, what="the deployment manifest")
    manifest_commit = str(manifest.get("commit", "")).strip().lower()
    if not _is_commit(manifest_commit):
        raise DeploymentEvidenceMissing(
            f"the deployment manifest at {manifest_path} records no valid commit "
            f"({manifest.get('commit')!r})")
    manifest_digest = manifest.get("image_digest")
    if "runtime_digest" in required and manifest_digest is None:
        raise DeploymentEvidenceMissing(
            f"the deployment manifest at {manifest_path} records no artifact digest, so it cannot be "
            f"reconciled with what the runtime is executing")
    if manifest_digest is not None and not _is_digest(manifest_digest):
        raise DeploymentEvidenceMismatch(
            f"the deployment manifest records an invalid artifact digest {manifest_digest!r}")

    # ── every identity present must agree ──
    if manifest_commit != commit:
        raise DeploymentEvidenceMismatch(
            f"the deployment manifest says commit {manifest_commit} but the running artifact was built "
            f"from {commit} — something is running that was not deployed")

    digests = {
        "embedded build stamp": _normalize_digest(build_digest) if build_digest else None,
        "runtime": _normalize_digest(runtime_digest) if runtime_digest else None,
        "deployment manifest": _normalize_digest(manifest_digest) if manifest_digest else None,
    }
    present = {source: value for source, value in digests.items() if value}
    if len(set(present.values())) > 1:
        detail = ", ".join(f"{source}={value}" for source, value in sorted(present.items()))
        raise DeploymentEvidenceMismatch(
            f"the artifact digests disagree ({detail}) — the running artifact is not the deployed one")
    agreed_digest = next(iter(present.values()), None)

    if expected_commit is not None:
        pinned = str(expected_commit).strip().lower()
        if pinned != commit:
            raise DeploymentEvidenceMismatch(
                f"the operator pinned commit {pinned} but the deployment identifies as {commit}")

    identity = DeploymentIdentityEvidence(
        model=model,
        embedded_build_commit=commit,
        embedded_build_tree_clean=True,
        embedded_build_digest=_normalize_digest(build_digest) if build_digest else None,
        build_info_source=str(build_path),
        runtime_artifact_digest=_normalize_digest(runtime_digest) if runtime_digest else None,
        runtime_digest_source=runtime_source,
        manifest_commit=manifest_commit,
        manifest_artifact_digest=_normalize_digest(manifest_digest) if manifest_digest else None,
        manifest_source=str(manifest_path),
        agreed_commit=commit,
        agreed_artifact_digest=agreed_digest,
        identity_digest="",
    )
    body = {k: v for k, v in asdict(identity).items() if k != "identity_digest"}
    body["model"] = str(model)
    return DeploymentIdentityEvidence(
        **{**body, "model": model,
           "identity_digest": hashlib.sha256(
               json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
           ).hexdigest()})
