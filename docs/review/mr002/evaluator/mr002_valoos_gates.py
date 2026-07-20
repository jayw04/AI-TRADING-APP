"""MR-002 validation/OOS evaluator — gate engine (Workstream B, Increment 1).

Deterministic verdict engine over caller-supplied metric results. Each entry is classified
GATE | DIAGNOSTIC | DESCRIPTIVE and given a status PASS | FAIL | N_A | ERROR. The window disposition
is a pure function of the GATE entries plus any refusal / integrity-stop signalled by the caller:
DIAGNOSTIC and DESCRIPTIVE entries are STRUCTURALLY unable to move the disposition.
"""

from __future__ import annotations

from dataclasses import dataclass, field

GATE = "GATE"
DIAGNOSTIC = "DIAGNOSTIC"
DESCRIPTIVE = "DESCRIPTIVE"

PASS = "PASS"
FAIL = "FAIL"
N_A = "N_A"
ERROR = "ERROR"

# window dispositions
DISP_PASS = "PASS"
DISP_FAIL = "FAIL"
DISP_REFUSED = "REFUSED"
DISP_INTEGRITY_STOP = "INTEGRITY_STOP"


@dataclass(frozen=True)
class GateResult:
    gate_id: str
    classification: str          # GATE | DIAGNOSTIC | DESCRIPTIVE
    status: str                  # PASS | FAIL | N_A | ERROR
    value: object
    threshold: object
    sample: object
    evidence: str

    def to_dict(self) -> dict:
        return {"gate_id": self.gate_id, "classification": self.classification, "status": self.status,
                "value": self.value, "threshold": self.threshold, "sample": self.sample,
                "evidence": self.evidence}


@dataclass
class GateBattery:
    entries: list = field(default_factory=list)

    def add(self, gate_id: str, classification: str, status: str, value=None, threshold=None,
            sample=None, evidence: str = "") -> None:
        if classification not in (GATE, DIAGNOSTIC, DESCRIPTIVE):
            raise ValueError(f"bad classification: {classification}")
        if status not in (PASS, FAIL, N_A, ERROR):
            raise ValueError(f"bad status: {status}")
        self.entries.append(GateResult(gate_id, classification, status, value, threshold, sample, evidence))

    def gate(self, gate_id: str, passed: bool, value=None, threshold=None, sample=None, evidence: str = ""):
        self.add(gate_id, GATE, PASS if passed else FAIL, value, threshold, sample, evidence)

    def diagnostic(self, gate_id: str, value=None, evidence: str = ""):
        # diagnostics are recorded with status N_A so they can never read as PASS/FAIL levers
        self.add(gate_id, DIAGNOSTIC, N_A, value, None, None, evidence)

    def descriptive(self, gate_id: str, value=None, evidence: str = ""):
        self.add(gate_id, DESCRIPTIVE, N_A, value, None, None, evidence)

    # ── disposition: pure function of GATE entries + refusal/integrity signals ─────────────────────
    def disposition(self, *, refused: bool = False, integrity_stop: bool = False) -> str:
        if refused:
            return DISP_REFUSED
        if integrity_stop:
            return DISP_INTEGRITY_STOP
        gate_entries = [e for e in self.entries if e.classification == GATE]
        if any(e.status == ERROR for e in gate_entries):
            return DISP_INTEGRITY_STOP
        if not gate_entries:
            # no gates evaluated is not a silent pass
            return DISP_INTEGRITY_STOP
        if all(e.status == PASS for e in gate_entries):
            return DISP_PASS
        return DISP_FAIL

    def to_list(self) -> list:
        return [e.to_dict() for e in self.entries]
