# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.12-slim

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

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8000/healthz >/dev/null || exit 1

# Self-bootstrap on first start: run migrations, then idempotent seed, then serve.
CMD ["sh", "-c", "alembic upgrade head && python scripts/seed_dev_data.py && uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000"]
