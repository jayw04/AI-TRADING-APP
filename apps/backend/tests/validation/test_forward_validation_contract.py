"""The source-controlled `forward_validation.json` contract must not drift from the loader.

The schema and example under `deploy/forward-validation/` are the only committed description of what
a deployment must provide. If `_REQUIRED_KEYS` gains a key and the schema does not, an operator builds
a configuration from the committed contract and the deployment refuses it at load — on the host, the
morning of an observation, rather than here.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.validation.forward_deployment_config import _REQUIRED_KEYS

CONTRACT_DIR = Path(__file__).resolve().parents[4] / "deploy" / "forward-validation"
SCHEMA = json.loads((CONTRACT_DIR / "forward_validation.schema.json").read_text(encoding="utf-8"))
EXAMPLE = json.loads((CONTRACT_DIR / "forward_validation.example.json").read_text(encoding="utf-8"))


def test_the_schema_requires_exactly_what_the_loader_requires():
    assert set(SCHEMA["required"]) == set(_REQUIRED_KEYS)


def test_the_example_provides_every_required_key():
    missing = [k for k in _REQUIRED_KEYS if EXAMPLE.get(k) in (None, "")]
    assert not missing, f"the committed example omits {sorted(missing)}"


def test_the_example_names_host_paths_not_repository_artifacts():
    """A committed copy of a governed artifact is a copy that can drift from the artifact it names."""
    for key in ("dgs3mo_path", "trial_ledger_path", "corpus_manifest_path",
                "dgs3mo_manifest_path", "build_info_path", "deployment_manifest_path"):
        value = EXAMPLE[key]
        assert not value.startswith("docs/"), f"{key} points into the repository: {value}"
        assert value.startswith("/"), f"{key} is not an absolute host path: {value}"


def test_the_example_never_names_account_4_as_the_ledger():
    assert EXAMPLE["ledger_account_id"] != 4


def test_the_example_pins_the_governed_capital_and_cost():
    """$100,000 governed; never the retired 84466.41 baseline. Cost is the registered 10 bps."""
    assert EXAMPLE["starting_capital"] == 100_000.0
    assert EXAMPLE["turnover_cost_bps"] == 10.0


def test_the_example_uses_a_full_kms_key_arn():
    key_id = EXAMPLE["witness"]["key_id"]
    assert key_id.startswith("arn:aws:kms:"), "aliases and bare key ids are refused by ADR 0046"


def test_the_example_points_at_the_operational_witness_prefix():
    """`witness/` is the operational prefix; `preflight/` holds synthetic receipts only (ADR 0047)."""
    assert EXAMPLE["witness"]["sink"]["options"]["prefix"] == "witness/"
