# MiroFish Backend — Production Dockerfile
# Flask API, Python 3.11, uv package manager

# ──────────────────────────────────────────
# Stage 1: dependency install
# ──────────────────────────────────────────
FROM python:3.11-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy lock files first — layer cache
COPY pyproject.toml uv.lock ./

# Install deps into /app/.venv (no dev extras)
RUN uv sync --frozen --no-dev

# ──────────────────────────────────────────
# Stage 2: runtime image
# ──────────────────────────────────────────
FROM python:3.11-slim AS production

RUN apt-get update && \
    apt-get install -y --no-install-recommends dumb-init curl && \
    rm -rf /var/lib/apt/lists/*

# Non-root user
RUN addgroup --system --gid 1001 mirofish && \
    adduser --system --uid 1001 --ingroup mirofish mirofish

WORKDIR /app

# Copy venv from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application source
COPY --chown=mirofish:mirofish app ./app
COPY --chown=mirofish:mirofish run.py ./

# Uploads dir must be writable (simulation data + file uploads)
RUN mkdir -p /app/uploads/simulations && \
    chown -R mirofish:mirofish /app/uploads

# Activate venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_HOST=0.0.0.0 \
    FLASK_PORT=5001 \
    FLASK_DEBUG=false

USER mirofish

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -sf http://localhost:5001/api/health || exit 1

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["python", "run.py"]
