"""Rebind FREEZE-MANIFEST-003 identities to published CAMPAIGN v1.2 tip."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

# PR #562 content tip and merge tip on main
CONTENT_TIP = "9b62abb98b8adbcf9713cee006201e45f3015deb"
MERGE_TIP = "974e374271aa04e0bd3d542faf856fcdddd3ff3c"
PR_URL = "https://github.com/jayw04/AI-TRADING-APP/pull/562"


def blob_sha256(rel: str, rev: str = CONTENT_TIP) -> str:
    data = subprocess.check_output(["git", "cat-file", "blob", f"{rev}:{rel}"])
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    manifest_path = (
        ROOT
        / "docs/design/ADR0043_Phase0_D_BOX_Freeze_Manifest_003_UNSEALED_DRAFT.json"
    )
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    body = doc["manifest_body"]

    campaign_sha = blob_sha256(
        "docs/design/ADR0043_Phase0_D_BOX_Campaign_Scope_v1.2.md"
    )
    adapter_sha = blob_sha256(
        "apps/backend/app/risk/loss_control/phase0_o34_archive_adapter.py"
    )
    validator_sha = blob_sha256(
        "apps/backend/scripts/adr0043_dbox_freeze_manifest.py"
    )
    validator_test_sha = blob_sha256(
        "apps/backend/tests/scripts/test_adr0043_dbox_freeze_manifest.py"
    )
    adapter_test_sha = blob_sha256(
        "apps/backend/tests/risk/test_phase0_o34_archive_adapter.py"
    )
    schema_sha = blob_sha256(
        "docs/design/schemas/ADR0043_Phase0_D_BOX_Freeze_Manifest.schema.json"
    )

    body["governing_refs"]["campaign_scope_sha256"] = campaign_sha
    body["schema_binding"]["commit"] = CONTENT_TIP
    body["schema_binding"]["sha256"] = schema_sha
    body["schema_binding"]["tooling_merge_commit"] = MERGE_TIP
    body["schema_binding"]["pr"] = PR_URL
    body["schema_binding"]["note"] = (
        "Rebound to published CAMPAIGN v1.2 content tip after PR #562 merge"
    )

    body["code_and_tools"]["freeze_manifest_validator"].update(
        {
            "commit": CONTENT_TIP,
            "sha256": validator_sha,
            "tests_sha256": validator_test_sha,
            "tooling_merge_commit": MERGE_TIP,
            "pr": PR_URL,
            "local_pytest_result": (
                "adapter + freeze-manifest tests green on PR tip; "
                "CI Python + FULL + Gate green on #562"
            ),
        }
    )
    hic = body["code_and_tools"]["harness_input_contract"]
    hic["adapter"].update(
        {
            "sha256": adapter_sha,
            "tests_sha256": adapter_test_sha,
            "commit": CONTENT_TIP,
        }
    )
    body["code_and_tools"]["harness_commit"] = CONTENT_TIP
    body["code_and_tools"]["deployment_commit"] = CONTENT_TIP
    body["code_and_tools"]["harness_commit_note"] = (
        "Isolated harness checkout at published content tip "
        f"{CONTENT_TIP} (merge {MERGE_TIP}). Production b0058bf "
        "reference-only FORBIDDEN to modify."
    )

    body["repository_state"] = {
        "git_commit_full": CONTENT_TIP,
        "merge_commit_full": MERGE_TIP,
        "implementation_baseline": (
            "d1c2fbf0a394c66728f6cc489577ae180ccdfb03"
        ),
        "working_tree": (
            "CLEAN_AT_PUBLISHED_TIP — FREEZE-003 tip-rebind commit may follow; "
            "content identities bound to PR #562 tip"
        ),
        "clean_tree_proof": (
            f"content tip {CONTENT_TIP} published via {MERGE_TIP} / PR #562"
        ),
        "worktree_path_local": "C:/LLM-RAG-APP/ai-trading-app-adr0043-ph0",
        "branch": "main",
        "submodules": "none",
        "publication_pr": PR_URL,
        "qualification_tip_on_main": (
            "646d81abfdd98ce4ca99dde7821a26e869a50824"
        ),
    }

    doc["seal"]["verifier_script"].update(
        {
            "commit": CONTENT_TIP,
            "sha256": validator_sha,
        }
    )
    doc["seal"]["manifest_status"] = "READY_UNSEALED"
    doc["seal"]["post_seal_state"] = (
        "READY_UNSEALED — tip rebound to published PR #562; seal not yet "
        "authorized in this step"
    )
    doc["seal"]["campaign_start"] = (
        "HOLD — requires separate owner start decision after seal"
    )

    manifest_path.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {manifest_path}")
    print(f"content_tip={CONTENT_TIP}")
    print(f"merge_tip={MERGE_TIP}")
    print(f"campaign_sha={campaign_sha}")
    print(f"adapter_sha={adapter_sha}")
    print(f"validator_sha={validator_sha}")
    print(f"schema_sha={schema_sha}")


if __name__ == "__main__":
    main()
