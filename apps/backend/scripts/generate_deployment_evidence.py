"""Generate `build_info.json` and `deployment_manifest.json` for a forward-validation deployment.

These two files are the only ones of the four required deployment inputs that are GENERATED. The
DGS3MO snapshot and the trial ledger are frozen by the countersigned preregistration and are installed
by exact hash — regenerating them produces different digests and the preflight refuses every session,
correctly (ADR 0048 (12)).

Everything written here is derived, never asserted. The commit comes from git, the cleanliness from
`git status --porcelain`, the artifact hashes from the files themselves. The one thing a caller may
supply is a PIN (`--expect-commit`), which can only narrow the result: if it disagrees with what the
tree actually is, the generator refuses rather than recording the pin.

Output is canonical JSON — sorted keys, no insignificant whitespace — so regenerating an unchanged
deployment reproduces byte-identical files, and a diff means something really changed.

Usage (from apps/backend):

    python scripts/generate_deployment_evidence.py \\
        --out-dir /opt/workbench/forward/evidence \\
        --corpus-manifest /opt/workbench/forward/corpus_manifest.json \\
        --dgs3mo-manifest /opt/workbench/forward/dgs3mo_manifest.json \\
        --config /etc/workbench/forward_validation.json

`--allow-dirty` records `tree_clean: false` honestly rather than refusing at generation time. The
deployment verifier still refuses to run a session on it; the flag exists so an operator can produce
evidence of a dirty tree for diagnosis, never to get one past the gate.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.validation.governed_corpus import (  # noqa: E402
    Layer2CorpusManifest,
    canonical_json,
    deployment_corpus_block,
    file_sha256,
    load_any_corpus_manifest,
    load_dgs3mo_manifest,
    load_layer2_countersignature,
    normalize_corpus_manifest,
    require_countersignature,
    verify_frozen_artifact,
)

#: The frozen Stage-2/3/4 replica the forward instrument imports. Their digests are recorded so a
#: session's evidence names the exact measurement code, not merely the repository commit.
REPLICA_SCRIPTS = (
    "scripts/backtest_momentum_stage2.py",
    "scripts/backtest_momentum_stage3.py",
    "scripts/backtest_momentum_stage4.py",
)


class GenerationError(RuntimeError):
    """The deployment could not be described truthfully. Nothing is written."""


def _git(*args: str, repo: Path) -> str:
    try:
        out = subprocess.run(("git", *args), cwd=repo, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise GenerationError(f"git {' '.join(args)} failed: {exc}") from exc
    return out.stdout.strip()


def _repo_root(start: Path) -> Path:
    root = _git("rev-parse", "--show-toplevel", repo=start)
    if not root:
        raise GenerationError(f"{start} is not inside a git working tree")
    return Path(root)


def _dependency_versions() -> dict[str, str]:
    """Versions of the packages a governed session's result actually depends on."""
    from importlib.metadata import PackageNotFoundError, version

    names = ("pandas", "numpy", "duckdb", "scikit-learn", "pandas-market-calendars",
             "cryptography", "boto3")
    out: dict[str, str] = {}
    for name in names:
        try:
            out[name] = version(name)
        except PackageNotFoundError:
            out[name] = "ABSENT"
    return out


def _package_hash(repo: Path) -> str:
    """A digest over the application package's tracked source. Names WHAT is running, where the
    commit only names what was reviewed — they differ the moment anything is edited in place."""
    listing = _git("ls-files", "apps/backend/app", repo=repo).splitlines()
    if not listing:
        raise GenerationError("git reports no tracked files under apps/backend/app")
    h_input = []
    for rel in sorted(listing):
        path = repo / rel
        if path.is_file():
            h_input.append(f"{rel}:{file_sha256(path)}")
    import hashlib

    return hashlib.sha256("\n".join(h_input).encode("utf-8")).hexdigest()


def build_info(repo: Path, *, allow_dirty: bool, expect_commit: str | None,
               image_digest: str | None) -> dict[str, Any]:
    commit = _git("rev-parse", "HEAD", repo=repo).lower()
    if len(commit) != 40:
        raise GenerationError(f"git returned an unusable commit {commit!r}")
    if expect_commit and expect_commit.strip().lower() != commit:
        raise GenerationError(
            f"the tree is at {commit} but --expect-commit pinned {expect_commit.strip().lower()}; "
            f"the pin narrows the result and never replaces it")
    dirty = bool(_git("status", "--porcelain", repo=repo))
    if dirty and not allow_dirty:
        raise GenerationError(
            f"the working tree at {repo} has uncommitted changes, so {commit} does not identify the "
            f"code being deployed; commit them or pass --allow-dirty to record the fact")

    payload: dict[str, Any] = {
        "commit": commit,
        "tree_clean": not dirty,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "python_version": platform.python_version(),
        "platform": f"{platform.system()}/{platform.machine()}",
        "dependency_versions": _dependency_versions(),
        "application_package_sha256": _package_hash(repo),
        "frozen_replica_sha256": {
            rel: file_sha256(repo / "apps/backend" / rel) for rel in REPLICA_SCRIPTS
            if (repo / "apps/backend" / rel).is_file()
        },
    }
    if image_digest:
        payload["image_digest"] = image_digest.strip().lower()
    missing = [r for r in REPLICA_SCRIPTS if not (repo / "apps/backend" / r).is_file()]
    if missing:
        raise GenerationError(
            f"the frozen Stage-2/3/4 replica is incomplete; missing {missing}. A session's evidence "
            f"cannot name measurement code that is not present")
    return payload


def deployment_manifest(repo: Path, *, build: dict[str, Any], corpus_manifest_path: Path,
                        dgs3mo_manifest_path: Path, config_path: Path,
                        host_identity: str | None, image_digest: str | None) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))

    # Whichever construction the deployment actually installed. The generator must be able to describe
    # a reconstruction as truthfully as a base-plus-delta chain — a generator that understands only one
    # of them produces a manifest the session path then refuses, which is how the two drift apart.
    corpus = load_any_corpus_manifest(corpus_manifest_path)
    normalized = normalize_corpus_manifest(corpus)
    dgs3mo = load_dgs3mo_manifest(dgs3mo_manifest_path)

    countersignature = None
    if isinstance(corpus, Layer2CorpusManifest):
        declared = str(config.get("corpus_countersignature_path", "") or "").strip()
        if not declared:
            raise GenerationError(
                "the deployment installed a Layer 2 reconstruction but its configuration names no "
                "corpus_countersignature_path; the external approval is part of what the deployment "
                "is authorized to assemble and is not optional for this construction kind")
        countersignature = load_layer2_countersignature(Path(declared))
        require_countersignature(corpus, countersignature)

    # The frozen inputs are verified HERE, at generation, as well as at session start. A manifest that
    # binds a drifted artifact would otherwise be produced happily and only refused a day later.
    from app.validation.forward_window import DGS3MO_SNAPSHOT_SHA256, TRIAL_LEDGER_SHA256

    dgs3mo_sha = verify_frozen_artifact(Path(config["dgs3mo_path"]),
                                        pinned_sha256=DGS3MO_SNAPSHOT_SHA256,
                                        what="the frozen DGS3MO base")
    ledger_sha = verify_frozen_artifact(Path(config["trial_ledger_path"]),
                                        pinned_sha256=TRIAL_LEDGER_SHA256,
                                        what="the governed trial ledger")

    witness = config.get("witness", {})
    sink_options = (witness.get("sink") or {}).get("options", {})

    payload: dict[str, Any] = {
        "commit": build["commit"],
        "created_at": build["created_at"],
        "build_info_sha256": "",          # filled by the caller once build_info.json is on disk
        # The authorized construction — ADR 0048 (8). Built by the SAME function
        # `resolve_governed_construction` recomputes it with, so a manifest this generator writes and
        # the block the session path expects cannot disagree about shape or content.
        #
        # Identities are surfaced INDEPENDENTLY rather than rolled up, so an operator reading a
        # mismatch can tell which component of the construction moved; a single digest would say only
        # "something changed".
        #
        # store_identity_sha256 is deliberately ABSENT: it does not exist until a session performs its
        # reads, and a manifest finalized before observation #1 cannot honestly carry one. It is
        # required in OBSERVATION evidence instead (ADR 0048 (7)).
        "corpus": deployment_corpus_block(
            normalized, dgs3mo_manifest_sha256=dgs3mo.dgs3mo_manifest_sha256,
            countersignature=countersignature),
        "frozen_inputs": {
            "dgs3mo_sha256": dgs3mo_sha,
            "trial_ledger_sha256": ledger_sha,
        },
        "program": {
            "account_id": 4,
            "strategy_id": config.get("strategy_id"),
            "ledger_account_id": config.get("ledger_account_id"),
        },
        "witness": {
            "key_id": witness.get("key_id"),
            "bucket": sink_options.get("bucket"),
            "prefix": sink_options.get("prefix"),
            "profile": witness.get("profile"),
        },
        "configuration_sha256": file_sha256(config_path),
        "host_identity": host_identity or platform.node(),
        "authorization_state": {
            # Recorded, never inferred. These are the standing owner rulings as of this generation.
            "forward_window_open": False,
            "hold_removed": False,
            "broker_orders_authorized": False,
            "account4_activation_authorized": False,
        },
    }
    if image_digest:
        payload["image_digest"] = image_digest.strip().lower()
    return payload


def _write_canonical(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = canonical_json(payload)
    path.write_bytes(blob)
    import hashlib

    return hashlib.sha256(blob).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--corpus-manifest", required=True, type=Path)
    ap.add_argument("--dgs3mo-manifest", required=True, type=Path)
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--expect-commit", default=None,
                    help="operator pin; narrows the result, never replaces it")
    ap.add_argument("--image-digest", default=None, help="sha256:… for CONTAINER deployments")
    ap.add_argument("--host-identity", default=None)
    ap.add_argument("--allow-dirty", action="store_true",
                    help="record tree_clean=false honestly instead of refusing; the session gate "
                         "still refuses to run on it")
    args = ap.parse_args(argv)

    try:
        repo = _repo_root(Path(__file__).resolve().parent)
        build = build_info(repo, allow_dirty=args.allow_dirty,
                           expect_commit=args.expect_commit, image_digest=args.image_digest)
        manifest = deployment_manifest(
            repo, build=build, corpus_manifest_path=args.corpus_manifest,
            dgs3mo_manifest_path=args.dgs3mo_manifest, config_path=args.config,
            host_identity=args.host_identity, image_digest=args.image_digest)

        build_path = args.out_dir / "build_info.json"
        build_sha = _write_canonical(build_path, build)
        manifest["build_info_sha256"] = build_sha
        manifest_path = args.out_dir / "deployment_manifest.json"
        manifest_sha = _write_canonical(manifest_path, manifest)
    except (GenerationError, OSError, KeyError, ValueError) as exc:
        print(json.dumps({"status": "REFUSED", "detail": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 1

    print(json.dumps({
        "status": "GENERATED",
        "build_info": {"path": str(build_path), "sha256": build_sha,
                       "commit": build["commit"], "tree_clean": build["tree_clean"]},
        "deployment_manifest": {"path": str(manifest_path), "sha256": manifest_sha},
        "corpus_manifest_sha256": manifest["corpus"]["corpus_manifest_sha256"],
        "dgs3mo_manifest_sha256": manifest["corpus"]["dgs3mo_manifest_sha256"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
