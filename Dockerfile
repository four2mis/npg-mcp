# ── Stage 1: Builder ────────────────────────────────────────────────
FROM python:3.11-slim AS builder
RUN pip install --no-cache-dir --upgrade pip setuptools wheel
WORKDIR /build
COPY pyproject.toml .
COPY npg_mcp/ npg_mcp/
COPY __init__.py .
RUN pip wheel --no-cache-dir --wheel-dir /wheelhouse .

# ── Stage 2: Runtime ────────────────────────────────────────────────
FROM python:3.11-slim
RUN useradd -m -s /bin/bash appuser
WORKDIR /app
COPY --from=builder /wheelhouse /wheelhouse
RUN pip install --no-cache-dir --no-index --find-links /wheelhouse "mcp>=1.0.0,<2.0.0" httpx npg-mcp
USER appuser
ENV MCP_TRANSPORT=http
EXPOSE 8081
CMD ["python", "-m", "npg_mcp.main"]
