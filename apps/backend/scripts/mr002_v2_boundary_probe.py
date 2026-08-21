"""PRE-CREDENTIAL BOUNDARY PROBE — the real S3 branch, stopped one line short.

Exercises the PRODUCTION path: production registry, production contract, journal, the
credential gate, `import boto3`, and `boto3.client("sts")` — then intercepts
acquire_reader_credentials and stops. Nothing assumes a role, nothing reads an object, and the
latch is never touched.

Two independent safeties, because one is not enough at this boundary:
  1. acquire_reader_credentials is replaced BEFORE the launcher imports it, so the real one is
     unreachable by this process.
  2. the container runs with --network=none, so even a call that somehow escaped the intercept
     could not reach STS.
The latch is a third, and it stays CLOSED throughout.
"""
import runpy, sys

sys.path.insert(0, "/work/apps/backend")
from app.research.mr002.phase3c import credential_readiness as CR


class ReachedCredentialBoundary(Exception):
    pass


REACHED = {"hit": False}


def _intercept(*a, **k):
    REACHED["hit"] = True
    raise ReachedCredentialBoundary("PROBE STOP: reached the credential boundary intentionally")


CR.acquire_reader_credentials = _intercept

sys.argv = ["mr002_phase3c_validation_run.py", "--reader", "s3", "--window", "validation",
            "--contract", "validation2",
            "--manifest", "/work/apps/backend/app/research/mr002/phase3c/manifests/"
                          "validation2_object_registry.json",
            "--materialized", "/out/probe.duckdb", "--journal", "/out/probe.journal.jsonl",
            "--out", "/out/probe.report.json"]

err = None
try:
    runpy.run_path("/work/apps/backend/scripts/mr002_phase3c_validation_run.py",
                   run_name="__main__")
except ReachedCredentialBoundary as e:
    err = str(e)
except BaseException as e:
    err = "%s: %s" % (type(e).__name__, e)

print("reached_credential_boundary:", REACHED["hit"])
print("stopped_with:", err)

import json
rows = [json.loads(x) for x in open("/out/probe.journal.jsonl") if x.strip()]
print("journal rows:", len(rows))
print("kinds:", [r["kind"] for r in rows])
reads = [r for r in rows if r["kind"] in ("read_intent", "read_verified")]
print("READ EVENTS (must be 0):", len(reads))
term = [r for r in rows if r["kind"] == "terminal"]
print("terminal:", [(t["disposition"], t.get("detail", "")[:60]) for t in term])
ok = REACHED["hit"] and len(reads) == 0
print()
print("BOUNDARY PROBE:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
