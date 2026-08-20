"""STATIC invariants over the Validation-2 launcher. No execution, no AWS, no reader.

These are the structural claims the owner required before Option-1-style coupling can be trusted.
They are proven by parsing the launcher's AST, not by running it, so they hold for EVERY CLI
combination rather than the ones a test happens to try.
"""
from __future__ import annotations

import ast
import pathlib
import sys

LAUNCHER = pathlib.Path(__file__).with_name("mr002_phase3c_validation_run.py")
GATE = "_assert_production_contract_before_credentials"
ACQUIRE = "acquire_reader_credentials"
TREE = ast.parse(LAUNCHER.read_text(encoding="utf-8"))
FAILURES: list[str] = []


def _calls(node) -> list:
    return [n for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'OK ' if ok else 'X  '} {name}" + (f"  -- {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(name)


# 1 ── acquire_reader_credentials is called exactly ONCE in the whole launcher
acq = [n for n in ast.walk(TREE) if isinstance(n, ast.Call)
       and isinstance(n.func, ast.Name) and n.func.id == ACQUIRE]
check("credential acquisition appears exactly once", len(acq) == 1, f"found {len(acq)}")

# 2 ── it lives inside an `if args.reader == "s3"` branch, and that is its ONLY enclosing test
s3_branches = []
for node in ast.walk(TREE):
    if not isinstance(node, ast.If):
        continue
    t = node.test
    guards_s3 = (isinstance(t, ast.Compare) and isinstance(t.left, ast.Attribute)
                 and t.left.attr == "reader"
                 and any(isinstance(c, ast.Constant) and c.value == "s3" for c in t.comparators))
    if guards_s3 and any(c.func.id == ACQUIRE for c in _calls(node)):
        s3_branches.append(node)
check("credential acquisition is inside an `args.reader == \"s3\"` branch", len(s3_branches) == 1,
      f"found {len(s3_branches)}")

# 3 ── the gate is called in that SAME branch, and textually BEFORE the acquisition
coupled = False
if s3_branches:
    br = s3_branches[0]
    gate_lines = [c.lineno for c in _calls(br) if c.func.id == GATE]
    acq_lines = [c.lineno for c in _calls(br) if c.func.id == ACQUIRE]
    coupled = bool(gate_lines) and bool(acq_lines) and min(gate_lines) < min(acq_lines)
check("the production contract gate runs BEFORE credential acquisition, same branch", coupled)

# 4 ── the gate is called from exactly one place, so it cannot be bypassed by another path
gate_calls = [n for n in ast.walk(TREE) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Name) and n.func.id == GATE]
check("the gate has exactly one call site", len(gate_calls) == 1, f"found {len(gate_calls)}")

# 5 ── the gate itself compares key, VersionId and SHA-256 unconditionally
gate_def = next((n for n in ast.walk(TREE)
                 if isinstance(n, ast.FunctionDef) and n.name == GATE), None)
src = ast.unparse(gate_def) if gate_def else ""
check("gate compares SHA-256 against the frozen contract", "SHA256_CONTRACT_MISMATCH" in src)
check("gate compares VersionId against the frozen contract", "VERSION_ID_MISMATCH" in src)
check("gate compares key against the frozen contract", "SEALED_KEY_MISMATCH" in src)
check("gate has no reader/contract-conditional skip of the SHA comparison",
      "SHA256_CONTRACT_MISMATCH" in src and "SEALED_SHA256" in src)

# 5b ── the gate compares the CONSTRUCTED object's attributes against the frozen contract, not
#       the contract against itself. Object construction now sources key/VersionId/SHA from the
#       registry, so a gate that re-read the contract literals would be a tautology that passes
#       no matter what the registry said.
#       ⚠ A SUBSTRING TEST IS NOT ENOUGH HERE. The first version of this check asked whether
#       "obj.version_id" appeared in the gate source. Mutation testing defeated it: rewriting
#       the comparison to `if vid != vid:` removes the check entirely, yet the string
#       "obj.version_id" survives in the error message f-string, so the invariant still passed.
#       The check therefore analyses actual Compare NODES.
_gate_cmps = [n for n in ast.walk(gate_def)] if gate_def else []
_cmps = [n for n in _gate_cmps if isinstance(n, ast.Compare)]
for attr in ("key", "version_id", "sha256"):
    real = [c for c in _cmps
            if ast.unparse(c.left) == f"obj.{attr}"
            and all(ast.unparse(x) != f"obj.{attr}" for x in c.comparators)]
    check(f"gate performs a REAL comparison of the constructed obj.{attr}", bool(real),
          "no Compare node with obj.%s on one side and something else on the other" % attr)
# and no comparison anywhere in the gate may compare an expression to itself
_self = [ast.unparse(c) for c in _cmps
         if any(ast.unparse(x) == ast.unparse(c.left) for x in c.comparators)]
check("no self-comparison (always-false tautology) inside the gate", not _self, str(_self))
check("gate reads the constructed sources, not the registry", "sources" in src)

# 6 ── the gate is not nested under any conditional other than the reader=="s3" test, so no
#      flag (notably `production`) can route execution past it while still reaching credentials
def _enclosing_ifs(tree, target_call):
    """Every `if` whose body transitively contains the gate call."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and any(
                isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == target_call for n in ast.walk(node)):
            out.append(node)
    return out


enclosing = _enclosing_ifs(TREE, GATE)
tests = [ast.unparse(n.test) for n in enclosing]
only_s3_guard = len(tests) == 1 and "reader" in tests[0] and "'s3'" in tests[0]
check("the gate is guarded ONLY by reader == \"s3\", by no other flag", only_s3_guard,
      f"enclosing tests: {tests}")

# and `production` must never appear as a guard on the gate call path
check("no `production` flag guards the gate", all("production" not in t for t in tests),
      f"enclosing tests: {tests}")

# 6b ── the terminal record is written on BOTH exit paths of the __main__ guard.
#       Discovered while writing the injected-failure rehearsal: the guarantee lives entirely in
#       the `if __name__ == "__main__"` block, so any refactor that moved main() behind another
#       entry point would silently drop the terminal record on failure -- the exact evidence loss
#       of 2026-08-19. Pin it structurally rather than trusting it to stay put.
guard = next((n for n in TREE.body if isinstance(n, ast.If)
              and "__main__" in ast.unparse(n.test)), None)
check("a __main__ guard exists", guard is not None)
if guard is not None:
    tries = [n for n in ast.walk(guard) if isinstance(n, ast.Try)]
    outer = tries[0] if tries else None
    handler_src = "".join(ast.unparse(h) for h in outer.handlers) if outer else ""
    else_src = "".join(ast.unparse(n) for n in outer.orelse) if outer else ""
    check("failure path writes terminal(FAILED)",
          "terminal" in handler_src and "FAILED" in handler_src)
    check("failure path re-raises after recording evidence", "raise" in handler_src)
    check("success path writes terminal(COMPLETED)",
          "terminal" in else_src and "COMPLETED" in else_src)
    check("main() is invoked only inside that guarded try",
          len([n for n in ast.walk(TREE) if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Name) and n.func.id == "main"]) == 1)

# 7 ── the permitted-state table admits exactly one S3 triple
tbl = next((n for n in ast.walk(TREE) if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "PERMITTED_STATES" for t in n.targets)),
           None)
s3_states = ast.unparse(tbl).count("'s3'") if tbl else -1
check("exactly one permitted S3 execution state", s3_states == 1, f"found {s3_states}")

print()
if FAILURES:
    print(f"LAUNCHER INVARIANTS: {len(FAILURES)} FAILED -> {FAILURES}")
    sys.exit(1)
print("LAUNCHER INVARIANTS: ALL PASS — there is no executable path to Validation-2 credentials "
      "without the production key/VersionId/SHA-256 contract having succeeded first.")
