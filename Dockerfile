# ==============================================================================
# OpenProject Community Edition MCP Server - Container Image
# Installs directly into system Python with layer-cached dependencies
# ==============================================================================

FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    TRANSPORT=http \
    PORT=8000 \
    MCP_HTTP_HOST=0.0.0.0

# Copy uv binary for fast, deterministic dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Install dependencies first for layer caching
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy source and install the package globally
COPY src/ ./src/
RUN uv pip install --system --no-cache --no-deps .

# Clean up uv binary and create non-root user
RUN rm /bin/uv && groupadd -r mcp && useradd -r -g mcp -d /app -s /sbin/nologin mcp

USER mcp

EXPOSE 8000

# Default entrypoint runs the MCP server
ENTRYPOINT ["openproject-ce-mcp"]
