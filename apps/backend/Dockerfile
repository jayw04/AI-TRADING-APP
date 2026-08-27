# syntax=docker/dockerfile:1.7

# EXACT patch, matching the CI interpreter and the constraints/ resolution tuple
# (CPython 3.12.13). A floating 3.12-slim would let the runtime base move independently
# of the graph CI verified. GITHUB-OPS-001 deterministic resolution.
# linux/amd64 digest at pin time: sha256:cab2dbf575e971934a81e4622f5aba17aa7929719bd7e31033a3a83b97fd0464
# (recorded for provenance; promote to a digest-pinned FROM when the release
#  process can rebuild against a fixed base without manual digest updates)
ARG PYTHON_VERSION=3.12.13-slim

FROM python:${PYTHON_VERSION} AS builder

WORKDIR /build

# Optional extra pip args — e.g. `--trusted-host pypi.org --trusted-host
# files.pythonhosted.org` to build behind a TLS-inspecting proxy (Norton) whose
# root the build container doesn't trust. Empty by default → no effect on CI /
# clean networks; set locally via docker-compose.override.yml build args.
ARG PIP_EXTRA_ARGS=""

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY pyproject.toml ./
COPY app ./app

RUN pip install ${PIP_EXTRA_ARGS} --upgrade pip \
 && pip install ${PIP_EXTRA_ARGS} --prefix=/install .


FROM python:${PYTHON_VERSION} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /install /usr/local

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts

RUN mkdir -p /app/data /app/bars_cache /app/strategies_user

# Bake the code identity INTO the image, derived from the very bytes COPY just placed at /app/app.
# Derived, not asserted: no build ARG, no environment variable, nothing an operator can supply at
# container creation. The startup gate re-derives this at boot and refuses on mismatch, which is what
# catches code edited into a running container or shadowed by a bind mount.
RUN python scripts/bake_code_identity.py

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8000/healthz >/dev/null || exit 1

# Self-bootstrap on first start: run migrations, then idempotent seed, then serve.
# ⚠ The identity gate runs BEFORE `alembic upgrade head`. Migrations and seeding are side effects on
# durable state; a container that cannot prove it is running the code it was built with must not reach
# them. `sh -c` chains on && , so a non-zero exit here stops the container.
CMD ["sh", "-c", "python scripts/verify_runtime_code_identity.py && alembic upgrade head && python scripts/seed_dev_data.py && uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000"]
