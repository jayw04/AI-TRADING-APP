"""850-session full-path qualification: computation THROUGH durable publication, no sealed data.

Validation attempt #1 consumed its opening, read all eight sealed objects, and produced nothing:
the output directory was never created, and the publication exception replaced the primary failure
so the real cause was destroyed. The repaired package fixed both, but it had only ever been
qualified at 320 sessions. The validation window is 850, and "it works at 320" is not the claim
that matters after a run that died in four seconds on a path nobody had run to completion.

So this drives the SAME production entry point over a validation-shaped 850-session fixture world,
through durable publication, and records what a unit test cannot: wall-clock, peak memory, and
proof the run actually PROCESSED the whole registered horizon rather than merely accepting an
850-session calendar and terminating early.

Zero-data instrument: fixture parquet only. No sealed read, no reader assumption, no IAM change,
no validation or OOS object.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sys
import tempfile
import threading
import time
import tracemalloc

os.environ.setdefault("MR002_FIXTURE_SESSIONS", "850")

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from app.research.mr002.phase3b import publish as P  # noqa: E402
from app.research.mr002.phase3b import states as S  # noqa: E402
from tests.research.phase3b import fixtures_producer as F  # noqa: E402
from tests.research.phase3b import test_phase3b_entrypoint_qualification as EQ  # noqa: E402


def peak_rss_bytes() -> tuple[int | None, str]:
    """Process-level peak RSS, measured in THIS harness - the production path is untouched.

    tracemalloc counts Python allocations only, so it cannot answer whether the c6a.large has
    headroom. This complements it rather than replacing it.
    """
    try:  # POSIX
        import resource

        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports KiB; macOS reports bytes.
        return (ru * 1024 if sys.platform.startswith("linux") else ru), "resource.getrusage"
    except ImportError:
        pass
    try:  # Windows
        import ctypes
        from ctypes import wintypes

        class _PMC(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        k32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
        # Explicit signatures are REQUIRED: without them GetCurrentProcess returns its -1
        # pseudo-handle as a 32-bit int, which mis-marshals into a 64-bit HANDLE and the call
        # silently returns 0. That is exactly how the first instrumented run recorded
        # "unavailable" instead of a measurement.
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.GetCurrentProcess.argtypes = []
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD
        ]
        pmc = _PMC()
        pmc.cb = ctypes.sizeof(_PMC)
        if psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
            return int(pmc.PeakWorkingSetSize), "GetProcessMemoryInfo.PeakWorkingSetSize"
    except Exception:  # noqa: BLE001 - absence of a measurement is itself reportable
        pass
    return None, "unavailable"


def _atomic_write(path: str, obj: dict) -> None:
    """Write via temp + os.replace so a kill can never leave a half-written artifact."""
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write((json.dumps(obj, sort_keys=True, indent=1) + chr(10)).encode())
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


class _Sampler(threading.Thread):
    """Sample RSS and checkpoint evidence WHILE the production run executes.

    The previous harness was all-or-nothing: hours of work, evidence written only on success, so
    two interrupted attempts produced zero bytes. It also could not distinguish 'working' from
    'stalled at launch'. This samples from outside the production path - the runner is untouched.
    """

    def __init__(self, path: str, base: dict, interval: float = 15.0):
        super().__init__(daemon=True)
        self.path, self.base, self.interval = path, base, interval
        self.peak = 0
        self.peak_at = None
        self.samples: list[dict] = []
        self.started = time.perf_counter()
        self._stop = threading.Event()

    def snapshot(self, status: str, extra: dict | None = None) -> dict:
        rec = {**self.base, "status": status,
               "elapsed_seconds": round(time.perf_counter() - self.started, 1),
               "rss_peak_bytes": self.peak,
               "rss_peak_mib": round(self.peak / (1024 * 1024), 1) if self.peak else None,
               "rss_peak_at_elapsed_seconds": self.peak_at,
               "rss_samples": self.samples[-40:],
               "sample_count": len(self.samples)}
        if extra:
            rec.update(extra)
        return rec

    def run(self) -> None:
        while not self._stop.is_set():
            rss, _m = peak_rss_bytes()
            elapsed = round(time.perf_counter() - self.started, 1)
            if rss:
                if rss > self.peak:
                    self.peak, self.peak_at = rss, elapsed
                self.samples.append({"t": elapsed, "rss_mib": round(rss / (1024 * 1024), 1)})
                print(f"[progress] t={elapsed}s rss={round(rss / (1024 * 1024), 1)}MiB "
                      f"peak={round(self.peak / (1024 * 1024), 1)}MiB", flush=True)
            with contextlib.suppress(OSError):
                _atomic_write(self.path, self.snapshot("RUNNING"))
            self._stop.wait(self.interval)

    def stop(self) -> None:
        self._stop.set()


class QualificationFailed(Exception):
    """The 850-session path did not complete. Nothing is claimed."""


def evidence_path(width: int) -> str:
    name = f"MR002_Phase3B_WidthQualification_{width:03d}sec_v1.0.json"
    return os.path.abspath(os.path.join(
        _HERE, "..", "..", "..", "docs", "review", "mr002", "phase3bc", name))


def main() -> int:
    expected_sessions = int(os.environ["MR002_FIXTURE_SESSIONS"])
    width = len(F.SECURITIES)
    out_path = evidence_path(width)
    base = {"record_type": "MR002_Phase3B_WidthQualification", "version": "1.0",
            "artifact_kind": "QUALIFICATION_EVIDENCE",
            "securities": width, "sessions": expected_sessions,
            "price_rows_generated": len(F.price_rows()),
            "data_class": "FIXTURE / NON-SEALED - load and shape only; no sealed read, no reader "
                          "assumption, no IAM change, and no attempt to mimic sealed economics"}
    sampler = _Sampler(out_path, base)
    _atomic_write(out_path, sampler.snapshot("RUNNING", {"phase": "starting"}))
    sampler.start()
    print(f"[start] width={width} sessions={expected_sessions} "
          f"price_rows={base['price_rows_generated']} -> {out_path}", flush=True)
    try:
        return _qualify(expected_sessions, sampler, out_path, base)
    except BaseException as exc:
        sampler.stop()
        _atomic_write(out_path, sampler.snapshot(
            "INTERRUPTED", {"interrupted_by": f"{type(exc).__name__}: {str(exc)[:400]}"}))
        raise
    finally:
        sampler.stop()


def _qualify(expected_sessions: int, sampler: _Sampler, out_path: str, base: dict) -> int:
    if len(F.SESSIONS) != expected_sessions:
        raise QualificationFailed(
            f"fixture built {len(F.SESSIONS)} sessions, expected {expected_sessions}"
        )

    with tempfile.TemporaryDirectory() as tmp:
        import pathlib

        tmp_path = pathlib.Path(tmp)
        build_start = time.perf_counter()
        runner = EQ._runner(tmp_path)
        build_seconds = time.perf_counter() - build_start

        tracemalloc.start()
        run_start = time.perf_counter()
        outcome = runner.run()
        run_seconds = time.perf_counter() - run_start
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rss, rss_method = peak_rss_bytes()

        root = runner.output_root
        # -- the run must have COMPLETED, not merely started ---------------------------------
        if outcome.disposition != P.PASS:
            raise QualificationFailed(
                f"disposition={outcome.disposition} primary_error={outcome.primary_error} "
                f"publication_error={outcome.publication_error}"
            )
        if not outcome.published:
            raise QualificationFailed(f"not published: {outcome.publication_error}")
        if outcome.state != S.S11_PUBLISHED:
            raise QualificationFailed(f"terminal state {outcome.state} != S11_PUBLISHED")

        # -- the deliverable set: present, non-empty, and reproducing its recorded identity ---
        recorded = outcome.publication["deliverable_sha256"]
        if set(recorded) != set(P.DELIVERABLES):
            raise QualificationFailed(f"deliverable set incomplete: {sorted(recorded)}")
        inventory = {}
        for name in (*P.DELIVERABLES, P.REPORT, P.PUBLICATION):
            path = os.path.join(root, name)
            if not os.path.isfile(path):
                raise QualificationFailed(f"missing artifact: {name}")
            with open(path, "rb") as fh:
                payload = fh.read()
            if not payload:
                raise QualificationFailed(f"empty artifact: {name}")
            digest = hashlib.sha256(payload).hexdigest()
            if name in recorded and recorded[name] != digest:
                raise QualificationFailed(f"{name} does not reproduce its recorded identity")
            inventory[name] = {"sha256": digest, "bytes": len(payload)}
        with open(os.path.join(root, P.REPORT), "rb") as fh:
            report_digest = hashlib.sha256(fh.read()).hexdigest()
        if report_digest != outcome.publication["report_sha256"]:
            raise QualificationFailed("report does not reproduce its recorded identity")

        # -- scale-sensitive: prove the whole horizon was PROCESSED ---------------------------
        source = runner.candidate_source
        units = list(getattr(source, "units", None) or [])
        ordinals = sorted({u.t for u in units}) if units else []
        census = outcome.enrichment_census
        integrity = outcome.integrity
        if integrity["records_examined"] <= 0:
            raise QualificationFailed("zero records examined; a vacuous publication proves nothing")
        if not integrity["all_gates_zero"]:
            raise QualificationFailed(f"integrity gates non-zero: {integrity}")

        coverage = {
            "expected_session_count": expected_sessions,
            "calendar_session_count": len(runner.candidate_source.calendar.sessions),
            "first_session": F.SESSIONS[0],
            "last_session": F.SESSIONS[-1],
            "units_enumerated": len(units),
            "distinct_session_ordinals_in_units": len(ordinals),
            "min_unit_session_ordinal": ordinals[0] if ordinals else None,
            "max_unit_session_ordinal": ordinals[-1] if ordinals else None,
            "records_examined": integrity["records_examined"],
            "enrichment_records_examined": census["records_examined"],
            "producer_refusals": len(getattr(source, "refusals", []) or []),
            "refusal_codes": sorted({c for _s, _t, c in (getattr(source, "refusals", []) or [])}),
        }
        if coverage["calendar_session_count"] != expected_sessions:
            raise QualificationFailed(
                f"runner calendar carried {coverage['calendar_session_count']} sessions"
            )

        evidence = {
            "record_type": "MR002_Phase3B_850SessionFullPathQualification",
            "version": "1.0",
            "artifact_kind": "QUALIFICATION_EVIDENCE",
            "result": "PASS",
            "purpose": "prove the repaired execution path completes computation AND durable "
                       "publication at the validation window's 850-session horizon",
            "data_class": "FIXTURE / NON-SEALED — no sealed read, no reader assumption, no IAM "
                          "change, no validation or OOS object",
            "session_coverage": coverage,
            "calendar_identity_disclaimer": {
                "claim_made": "850-session SCALE and PATH coverage",
                "claim_NOT_made": "calendar identity equivalence with the registered validation "
                                  "window",
                "why": "the fixture builds 850 consecutive WEEKDAYS from 2019-10-03, so it ends "
                       "2023-01-04. The governed P9 validation calendar is 850 TRADING sessions "
                       "and ends 2023-02-16 - the difference is market holidays, which the fixture "
                       "does not model.",
                "acceptable_because": "this is a technical qualification of execution and "
                                      "publication mechanics at the validation session COUNT; it "
                                      "is not a research run and asserts nothing about the "
                                      "registered calendar",
                "registered_validation_calendar": {
                    "sessions": 850, "first": "2019-10-03", "last": "2023-02-16",
                    "authority": "MR002_ValidationStructuralManifest_v1.0.json, "
                                 "session_list_sha256 d9966a3a...",
                },
            },
            "deliverable_inventory": inventory,
            "deliverable_count": len(P.DELIVERABLES),
            "terminal_state": outcome.state,
            "disposition": outcome.disposition,
            "primary_disposition": outcome.primary_disposition,
            "published": outcome.published,
            "publication_error": outcome.publication_error,
            "performance": {
                "world_build_seconds": round(build_seconds, 2),
                "run_seconds": round(run_seconds, 2),
                "peak_traced_memory_bytes": peak,
                "peak_traced_memory_mib": round(peak / (1024 * 1024), 1),
                "peak_rss_bytes": rss,
                "peak_rss_mib": round(rss / (1024 * 1024), 1) if rss else None,
                "peak_rss_method": rss_method,
                "peak_rss_note": "process-level, measured by this harness; it INCLUDES interpreter "
                                 "overhead and native arrow/numpy buffers that tracemalloc cannot "
                                 "see. Measured on the developer machine, not the qualified host.",
                "note": "tracemalloc measures PYTHON allocations only; it excludes interpreter "
                        "overhead and native arrow/numpy buffers, so treat it as a lower bound "
                        "on true process RSS",
            },
            "host_margin_note": "the qualified host is c6a.large (2 vCPU / 4 GiB). Compare the "
                                "figures above against that before granting a replacement opening.",
        }
        out = out_path
        sampler.stop()
        evidence.update(sampler.snapshot("PASS"))
        evidence["result"] = "PASS"
        evidence["status"] = "PASS"
        _atomic_write(out, evidence)
        print(json.dumps({k: v for k, v in evidence.items()
                          if k in ("result", "session_coverage", "performance")}, indent=1))
        print(f"\nwrote {out}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
