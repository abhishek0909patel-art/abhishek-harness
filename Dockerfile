# Production Dockerfile for Zero-Shot Agent (UP Police analyst capability).
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/root/.local/bin:$PATH

# System deps minimal (build tools removed in favour of wheels).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

# Install uv (works as module in PATH here).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# First copy only dependency manifests so dependency install is best cached.
COPY pyproject.toml uv.lock ./

# Install all deps (runtime + dev). This includes uvicorn, fastapi, pandas,
# numpy, plotly, matplotlib, pytest, etc. If image size matters, switch to
# `uv sync --frozen --no-dev` for runtime-only images.
RUN uv sync --frozen

# Application source (non-sensitive).
COPY src/ ./src/
COPY frontend/ ./frontend/
COPY agent.py ./

# Runtime data directories the app writes to at runtime.
RUN mkdir -p /app/data /app/data/uploads && chmod 0777 /app/data /app/data/uploads

EXPOSE 8001

# Use the python from uv's venv at runtime.
ENV PATH=/app/.venv/bin:$PATH

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["python", "-m", "src"]
