# ── Stage 1: Builder ─────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install .

COPY . .
RUN pip install --no-cache-dir --prefix=/install .

# ── Stage 2: Runtime ────────────────────────────────────────
FROM python:3.12-slim AS runtime

RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 rayolly && \
    useradd --uid 1000 --gid rayolly --shell /bin/bash --create-home rayolly

COPY --from=builder /install /usr/local
COPY --from=builder /build/rayolly /app/rayolly
COPY --from=builder /build/migrations /app/migrations

WORKDIR /app

RUN chown -R rayolly:rayolly /app

USER rayolly

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD ["curl", "-f", "http://localhost:8080/health"]

ENTRYPOINT ["uvicorn", "rayolly.main:app", \
    "--host", "0.0.0.0", \
    "--port", "8080", \
    "--loop", "uvloop", \
    "--http", "httptools", \
    "--workers", "1"]
