# MR-002 v1.1 — FROZEN RESEARCH RUNTIME (Linux/amd64)
#
# Registered by MR-002 Pre-Registration v1.1 rev 3, Appendix B.6 (countersigned
# 2026-07-12, artifact sha256 311e997b92858a7ede9f486ee7da11969703fc0304b2e6eb5c778ed8304f9dd5).
#
# This is a STANDALONE, OFFLINE research image. It is deliberately NOT the workbench
# Compose stack:
#   - no live database          - no broker connection
#   - no market-data websocket  - no application code paths
# The frozen research store is mounted READ-ONLY at run time.
#
# The solver-runtime manifest emitted from inside this image — not the developer
# workstation — is the authoritative execution record.

FROM python@sha256:fcbd8dfc2605ba7c2eca646846c5e892b2931e41f6227985154a596f26ab8ed7

# ---------------------------------------------------------------------------
# Determinism controls (Appendix B.5). Set here AND asserted at process start.
# ---------------------------------------------------------------------------
ENV OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    PYTHONHASHSEED=0 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /work

# ---------------------------------------------------------------------------
# Pinned direct dependencies. `--report` captures the resolved artifact URLs and
# their sha256 hashes for EVERY package (including the Linux quadprog wheel/sdist),
# written inside the image so the manifest cannot be forged from outside it.
# ---------------------------------------------------------------------------
COPY requirements.txt /manifest/requirements.txt

RUN mkdir -p /manifest \
 && pip install --no-cache-dir --report /manifest/pip_report.json \
      -r /manifest/requirements.txt \
 && pip freeze --all > /manifest/requirements.lock

COPY solver_manifest.py /manifest/solver_manifest.py

# The joint-solve implementation, fixtures and runner are bind-mounted at run time
# from apps/backend/ so the image stays stable across code iterations while the
# RUNTIME (which is what the manifest attests) remains byte-frozen.
ENV PYTHONPATH=/work/apps/backend

CMD ["python", "/manifest/solver_manifest.py"]
