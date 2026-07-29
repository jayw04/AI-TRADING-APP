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

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY pyproject.toml ./
COPY src ./src
COPY README.md ./

RUN pip install --upgrade pip \
 && pip install --prefix=/install .


FROM python:${PYTHON_VERSION} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WBMCP_HOST=0.0.0.0 \
    WBMCP_PORT=8766

WORKDIR /app

COPY --from=builder /install /usr/local

COPY src ./src

EXPOSE 8766

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD python -c "import socket,sys; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1', 8766)); s.close()" || exit 1

CMD ["mcp-workbench"]
