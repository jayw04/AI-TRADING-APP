"""MR-002 validation/OOS evaluator — gate engine (Increment 1 v1.1).

Deterministic verdict engine. A disposition is derived ONLY when EVERY governing gate in the
required-gate registry is present with the registry-pinned threshold and sample. Two distinct
outputs are produced:

  research_gate_verdict ∈ {PASS, FAIL}         — from the GATE entries alone
  run_disposition       ∈ {PASS, FAIL, REFUSED, INTEGRITY_STOP}  — publication decision

A required diagnostic that cannot be computed makes research_gate_verdict=PASS but
run_disposition=INTEGRITY_STOP (no confirmatory PASS published). Diagnostics never move the research
verdict. Enforcement errors (missing/duplicate/unknown/sample/threshold/ERROR gate) hard-stop or
refuse BEFORE any verdict is read.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mr002_valoos_registry import REQUIRED_DIAGNOSTICS, REQUIRED_GATES, _passes

GATE = "GATE"
DIAGNOSTIC = "DIAGNOSTIC"
DESCRIPTIVE = "DESCRIPTIVE"

PASS = "PASS"
FAIL = "FAIL"
N_A = "N_A"
ERROR = "ERROR"

DISP_PASS = "PASS"
DISP_FAIL = "FAIL"
DISP_REFUSED = "REFUSED"
DISP_INTEGRITY_STOP = "INTEGRITY_STOP"


class GateEnforcementStop(Exception):
    """Raised with an INTEGRITY_STOP:* or REFUSED_CODE_OR_DATA_IDENTITY:* code before a verdict."""


@dataclass(frozen=True)
class GateResult:
    gate_id: str
    classification: str
    status: str
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
    diagnostics: list = field(default_factory=list)

    # ── registration ──────────────────────────────────────────────────────────────────────────────
    def add_gate(self, gate_id: str, value=None, *, sample: str, error: bool = False, evidence: str = ""):
        """Register a GATE entry. Pass error=True if the metric computation failed (→ ERROR status).
        Otherwise pass/fail is derived from the registry threshold + comparison."""
        spec = REQUIRED_GATES.get(gate_id)
        if spec is None:
            self.entries.append(GateResult(gate_id, GATE, ERROR, value, None, sample, "UNKNOWN_GATE"))
            return
        if error:
            status = ERROR
        else:
            status = PASS if _passes(spec.comparison, value, spec.threshold) else FAIL
        self.entries.append(GateResult(gate_id, GATE, status, value, spec.threshold, sample, evidence))

    def add_diagnostic(self, diag_id: str, value=None, *, error: bool = False, evidence: str = ""):
        self.diagnostics.append({"diag_id": diag_id, "value": value,
                                 "status": ERROR if error else N_A,
                                 "classification": DIAGNOSTIC, "evidence": evidence})

    def add_descriptive(self, name: str, value=None):
        self.entries.append(GateResult(name, DESCRIPTIVE, N_A, value, None, None, ""))

    # ── enforcement + verdict ─────────────────────────────────────────────────────────────────────
    def _enforce_completeness(self):
        gate_entries = [e for e in self.entries if e.classification == GATE]
        seen: dict[str, int] = {}
        for e in gate_entries:
            seen[e.gate_id] = seen.get(e.gate_id, 0) + 1
        for gid, c in seen.items():
            if c > 1:
                raise GateEnforcementStop(f"INTEGRITY_STOP:DUPLICATE_GATE:{gid}")
            if gid not in REQUIRED_GATES:
                raise GateEnforcementStop(f"INTEGRITY_STOP:UNKNOWN_GATE:{gid}")
        for gid in REQUIRED_GATES:
            if gid not in seen:
                raise GateEnforcementStop(f"INTEGRITY_STOP:MISSING_REQUIRED_GATE:{gid}")
        for e in gate_entries:
            spec = REQUIRED_GATES[e.gate_id]
            if e.sample != spec.sample:
                raise GateEnforcementStop(
                    f"INTEGRITY_STOP:GATE_SAMPLE_MISMATCH:{e.gate_id}:{e.sample}!={spec.sample}")
            if e.status != ERROR and e.threshold != spec.threshold:
                raise GateEnforcementStop(
                    f"REFUSED_CODE_OR_DATA_IDENTITY:GATE_THRESHOLD:{e.gate_id}:{e.threshold}!={spec.threshold}")
            if e.status == ERROR:
                raise GateEnforcementStop(f"INTEGRITY_STOP:GATE_COMPUTATION_ERROR:{e.gate_id}")

    def _enforce_diagnostics(self):
        present = {d["diag_id"]: d for d in self.diagnostics}
        for did in REQUIRED_DIAGNOSTICS:
            d = present.get(did)
            if d is None:
                raise GateEnforcementStop(f"INTEGRITY_STOP:DIAGNOSTIC_COMPUTATION_ERROR:MISSING:{did}")
            if d["status"] == ERROR:
                raise GateEnforcementStop(f"INTEGRITY_STOP:DIAGNOSTIC_COMPUTATION_ERROR:{did}")

    def research_gate_verdict(self) -> str:
        """PASS iff every required GATE entry is PASS. Completeness enforced first."""
        self._enforce_completeness()
        gate_entries = [e for e in self.entries if e.classification == GATE]
        return PASS if all(e.status == PASS for e in gate_entries) else FAIL

    def evaluate(self, *, refused: bool = False) -> dict:
        """Return {research_gate_verdict, run_disposition, stop_code}. Diagnostics can only DEMOTE a
        PASS to INTEGRITY_STOP for publication — never flip a FAIL to PASS."""
        if refused:
            return {"research_gate_verdict": None, "run_disposition": DISP_REFUSED, "stop_code": None}
        try:
            verdict = self.research_gate_verdict()      # enforces gate completeness
            self._enforce_diagnostics()                 # required diagnostics must be computable
        except GateEnforcementStop as exc:
            code = str(exc)
            disp = DISP_REFUSED if code.startswith("REFUSED") else DISP_INTEGRITY_STOP
            # research verdict may still be computable if only diagnostics failed
            rgv = None
            if code.startswith("INTEGRITY_STOP:DIAGNOSTIC_COMPUTATION_ERROR"):
                try:
                    rgv = self.research_gate_verdict()
                except GateEnforcementStop:
                    rgv = None
            return {"research_gate_verdict": rgv, "run_disposition": disp, "stop_code": code}
        return {"research_gate_verdict": verdict, "run_disposition": verdict, "stop_code": None}

    # ── serialization ─────────────────────────────────────────────────────────────────────────────
    def to_list(self) -> list:
        return [e.to_dict() for e in self.entries]

    def diagnostics_list(self) -> list:
        return list(self.diagnostics)
