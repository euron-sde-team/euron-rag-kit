# syntax=docker/dockerfile:1.7
# API, job worker, migration runner and operator CLI: one image.
#   docker build -f infra/docker/api.Dockerfile -t ragkit-api .
#
#   api      uvicorn ragkit_server.main:create_app --factory   (default command)
#   worker   python -m ragkit_server.worker
#   cli      ragkit-server migrate | ragkit-server demo seed | ragkit-server reindex
#
# The bundled embedding model, the cross-encoder reranker and the tokenizer are baked in at
# build time, so a running container never downloads anything to index, rerank or answer.
ARG PYTHON_IMAGE=python:3.12.15-slim-bookworm
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.4

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS build
ARG EMBEDDINGS_MODEL=BAAI/bge-small-en-v1.5
ARG RERANKER_MODEL=Xenova/ms-marco-MiniLM-L-6-v2
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    EMBEDDINGS_CACHE_DIR=/app/models/fastembed TIKTOKEN_CACHE_DIR=/app/models/tiktoken
WORKDIR /src
# Dependencies first: this layer is reused until the lockfile changes. The SDK is only a
# development dependency of the server, so it is never installed here.
COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
# Models next: they depend on the libraries only, so a source change never downloads them again.
RUN /app/.venv/bin/python -c "import os, tiktoken; \
from fastembed import TextEmbedding; \
from fastembed.rerank.cross_encoder import TextCrossEncoder; \
cache = os.environ['EMBEDDINGS_CACHE_DIR']; \
TextEmbedding('${EMBEDDINGS_MODEL}', cache_dir=cache); \
TextCrossEncoder('${RERANKER_MODEL}', cache_dir=cache); \
tiktoken.get_encoding('o200k_base')"
COPY apps/api/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM ${PYTHON_IMAGE} AS runtime
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=UTC \
    EMBEDDINGS_CACHE_DIR=/app/models/fastembed TIKTOKEN_CACHE_DIR=/app/models/tiktoken \
    HF_HUB_OFFLINE=1 STORAGE_DIR=/tmp/ragkit/files
# Only these peers may set the client address through X-Forwarded-For (uvicorn reads this
# variable). The AWS deployment lists the VPC range, so the address the load balancer
# appends is used and anything a client prepends is ignored. Never "*".
ENV FORWARDED_ALLOW_IPS=127.0.0.1
# tini forwards SIGTERM, so uvicorn drains requests and the worker hands its jobs back.
RUN apt-get update && apt-get install -y --no-install-recommends tini ca-certificates libgomp1 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 10001 --user-group --no-create-home --home-dir /app ragkit
WORKDIR /app
COPY --from=build --chown=ragkit:ragkit /app/.venv /app/.venv
COPY --from=build --chown=ragkit:ragkit /app/models /app/models
# The demo seeder reads the sample corpus and datasets from ./samples.
COPY --chown=ragkit:ragkit samples /app/samples
USER ragkit
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=60s --retries=3 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/livez', timeout=2).status == 200 else 1)"]
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "ragkit_server.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", \
     "--proxy-headers", "--timeout-graceful-shutdown", "20", "--no-access-log"]
