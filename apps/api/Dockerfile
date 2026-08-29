FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
WORKDIR /workspace

COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY packages/domain/pyproject.toml packages/domain/pyproject.toml
COPY packages/workflows/pyproject.toml packages/workflows/pyproject.toml
COPY packages/retrieval/pyproject.toml packages/retrieval/pyproject.toml
COPY packages/providers/pyproject.toml packages/providers/pyproject.toml
COPY packages/exporters/pyproject.toml packages/exporters/pyproject.toml
RUN uv sync --frozen --package character-vein-api --no-dev --no-install-workspace

COPY apps/api apps/api
COPY packages packages
COPY data/jiezi/selection.json data/jiezi/selection.json
RUN uv sync --frozen --package character-vein-api --no-dev

RUN chmod +x apps/api/docker-entrypoint.sh apps/api/glyph-seed-entrypoint.sh apps/api/evidence-seed-entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["apps/api/docker-entrypoint.sh"]
