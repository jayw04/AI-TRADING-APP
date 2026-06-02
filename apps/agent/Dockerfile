# syntax=docker/dockerfile:1.7
#
# P6 §1a — agent service skeleton. The agent is a CONSUMER (it calls the backend
# HTTP API + workbench-mcp SSE), not a server: no EXPOSE, no healthcheck port.
# §1b wires the entrypoint that runs the proposal-generation loop; in §1a the
# container builds and the module imports cleanly, nothing more.

ARG PYTHON_VERSION=3.12-slim

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
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /install /usr/local

COPY src ./src

# §1a stub: 1b replaces this with the proposal-generation entrypoint.
CMD ["python", "-m", "agent"]
