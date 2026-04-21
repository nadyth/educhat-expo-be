# ---- Base ----
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini alembic.ini
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---- Development ----
FROM base AS development

ENV PATH="/app/.venv/bin:$PATH"

# Install dev dependencies for hot reload (watchfiles etc.)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

ARG TARGETARCH

# Install cloudflared for quick tunnel (dev only)
ADD https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${TARGETARCH}.deb /tmp/cloudflared.deb
RUN dpkg -i /tmp/cloudflared.deb && rm /tmp/cloudflared.deb

CMD ["python", "-c", "from app.main import run; run()"]

# ---- Production ----
FROM python:3.12-slim AS production

WORKDIR /app

COPY --from=base /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini alembic.ini

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]