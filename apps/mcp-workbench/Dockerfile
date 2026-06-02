# syntax=docker/dockerfile:1.7

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
