"""MR-002 Stage-3 — formal `_qp_matrices` input-contract conformance (cycle-5 finding 4).

Proves that `validate_model_inputs` enforces EVERY clause of the formal derived contract
(`stage3_cascade.INPUT_CONTRACT`): each clause has a boundary fixture violating exactly that
precondition, and the validator must reject it with the clause's declared defect code. A final test
asserts the contract's enforced_by codes and the validator's reachable codes are one-to-one, so a
clause can be neither silently dropped from the validator nor added without a contract entry.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.research.mr002 import stage3_cascade as sc

GOOD = (np.array([0.008, 0.008]), np.array([[1.0, 1.0]]), np.array([0.01]),
        np.zeros((0, 2)), np.zeros(0), np.array([0.02, 0.02]))


def _mut(i, val):
    r = list(GOOD)
    r[i] = val
    return tuple(r)


# one boundary fixture per contract clause, violating exactly that precondition
CLAUSE_FIXTURES = {
    "ARITY6": GOOD[:5],
    "CONVERTIBLE": _mut(0, np.array(["a", "b"], dtype=object)),
    "T_1D_NONEMPTY": _mut(0, np.zeros(0)),
    "AUB_2D_NCOLS": _mut(1, np.array([[1.0, 1.0, 1.0]])),          # 3 cols, n=2
    "AEQ_2D_NCOLS": _mut(3, np.zeros((1, 3))),
    "BUB_MATCH": _mut(2, np.array([0.01, 0.02])),                  # 2 entries, m_ub=1
    "BEQ_MATCH": _mut(4, np.array([0.5])),                         # 1 entry, meq=0
    "UPPER_1D_N": _mut(5, np.array([0.02])),                       # 1 entry, n=2
    "ALL_FINITE": _mut(2, np.array([np.inf])),
    "T_POSITIVE": _mut(0, np.array([0.008, 0.0])),                 # boundary: exactly zero
    "UPPER_NONNEG": _mut(5, np.array([0.02, -1e-12])),             # boundary: barely negative
}


@pytest.mark.parametrize("clause", sc.INPUT_CONTRACT["clauses"], ids=lambda c: c["id"])
def test_every_contract_clause_is_enforced(clause):
    fixture = CLAUSE_FIXTURES[clause["id"]]
    defect = sc.validate_model_inputs(fixture)
    assert defect is not None, f"clause {clause['id']} not enforced"
    assert defect.startswith(clause["enforced_by"]), (clause["id"], defect)


def test_valid_model_passes_every_clause():
    assert sc.validate_model_inputs(GOOD) is None


def test_empty_constraint_conventions_are_valid():
    # meq == 0 (GOOD already) and m_ub == 0 are both permitted zero-row 2-D conventions
    no_ineq = (GOOD[0], np.zeros((0, 2)), np.zeros(0), GOOD[3], GOOD[4], GOOD[5])
    assert sc.validate_model_inputs(no_ineq) is None


def test_contract_and_validator_codes_are_one_to_one():
    contract_codes = {c["enforced_by"] for c in sc.INPUT_CONTRACT["clauses"]}
    # the validator's reachable defect-code prefixes, from its source
    import inspect
    src = inspect.getsource(sc.validate_model_inputs)
    import re
    validator_codes = set(re.findall(r'return f?"([A-Z_]+)', src))
    validator_codes = {c.rstrip(":") for c in validator_codes}
    assert contract_codes == validator_codes, (
        f"contract-only: {contract_codes - validator_codes}; "
        f"validator-only: {validator_codes - contract_codes}")


def test_contract_metadata():
    assert sc.INPUT_CONTRACT["record_type"] == "MR002_STAGE3_QP_MATRICES_INPUT_CONTRACT"
    assert sc.INPUT_CONTRACT["version"] == "1.0"
    assert len(sc.INPUT_CONTRACT["clauses"]) == len(CLAUSE_FIXTURES)
