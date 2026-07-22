# ==========================================
# Stage 1 - Builder
# ==========================================

FROM python:3.11-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/appuser \
    XDG_CACHE_HOME=/home/appuser/.cache

# Build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        curl \
        libatomic1 && \
    rm -rf /var/lib/apt/lists/*

# Python virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY app ./app
COPY README.md .

# --------------------------------------------------
# Create application user BEFORE Prisma generation
# --------------------------------------------------
RUN addgroup --system appgroup && \
    adduser --system \
        --ingroup appgroup \
        --home /home/appuser \
        appuser && \
    mkdir -p /home/appuser/.cache/prisma-python && \
    chown -R appuser:appgroup \
        /home/appuser \
        /app \
        /opt/venv

USER appuser

# Generate Prisma client
RUN prisma generate --schema=app/prisma/schema.prisma

# Download Prisma Query Engine
RUN prisma py fetch


# ==========================================
# Stage 2 - Runtime
# ==========================================

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/appuser \
    XDG_CACHE_HOME=/home/appuser/.cache

# Runtime dependencies only
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        libatomic1 && \
    rm -rf /var/lib/apt/lists/*

# Copy Python virtual environment
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy downloaded Prisma binaries/cache
COPY --from=builder /home/appuser/.cache /home/appuser/.cache

# Copy application
COPY app ./app
COPY README.md .

# Create runtime user
RUN addgroup --system appgroup && \
    adduser --system \
        --ingroup appgroup \
        --home /home/appuser \
        appuser && \
    chown -R appuser:appgroup \
        /home/appuser \
        /app \
        /opt/venv

USER appuser

EXPOSE 8000

HEALTHCHECK \
    --interval=30s \
    --timeout=10s \
    --start-period=30s \
    --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
