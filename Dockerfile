# Dockerfile
# ─────────────────────────────────────────────────────────────────────────────
# Multi-stage build.
# Stage 1 — install Python dependencies into /install
# Stage 2 — lean runtime image, copy installed packages + source
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL description="Mini Cloud Storage — FastAPI + Gunicorn"

WORKDIR /app

# Runtime lib for psycopg2 (no compiler needed here)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY api/   api/
COPY db/    db/
COPY core/  core/

# Storage volume mount point
RUN mkdir -p /app/storage

# Non-root user for security
RUN useradd -m -u 1001 appuser \
    && chown -R appuser /app
USER appuser

EXPOSE 8000

# Gunicorn with Uvicorn workers
# --workers 4 is a sensible default; tune via WEB_CONCURRENCY env var
CMD ["gunicorn", "api.main:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "300", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
