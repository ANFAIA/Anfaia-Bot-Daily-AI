# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System dependencies required by asyncpg and occasional source builds.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Pip extras to install (e.g. "deepagents" for WORKFLOW_ENGINE=deepagents).
# Leave empty for a minimal image with only the sequential engine.
ARG INSTALL_EXTRAS=deepagents

# Install dependencies first to leverage layer caching.
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --upgrade pip \
    && if [ -n "$INSTALL_EXTRAS" ]; then pip install ".[$INSTALL_EXTRAS]"; else pip install .; fi

# Copy the rest of the project (alembic, entrypoint, etc.).
COPY alembic.ini ./
COPY alembic ./alembic
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Unprivileged user.
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import httpx,sys; sys.exit(0 if httpx.get('http://localhost:8000/health').status_code==200 else 1)"

ENTRYPOINT ["entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
