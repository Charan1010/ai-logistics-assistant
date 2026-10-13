# syntax=docker/dockerfile:1
# Multi-stage build: packages are installed in a builder stage, then only the
# virtualenv is copied into a clean runtime image. The final image has no pip
# cache, no compilers, and runs as a non-root user.

# ---- Stage 1: builder ----
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build tools for any dependency that ships only a source distribution.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---- Stage 2: runtime ----
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Copy only the installed virtualenv from the builder — no build toolchain.
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY app ./app
COPY tests ./tests
COPY .env.example ./

# Non-root user owns the app and the data directory (Chroma persistence).
RUN useradd --create-home appuser \
    && mkdir -p /app/data \
    && chown -R appuser /app
USER appuser

EXPOSE 8000

# Liveness probe hits the lightweight /api/health route (no external deps).
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
