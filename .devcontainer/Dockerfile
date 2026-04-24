# Base image
FROM mcr.microsoft.com/devcontainers/python:3.13-bookworm

# Grab pre-built binaries for bun and uv
COPY --from=oven/bun:latest /usr/local/bin/bun /usr/local/bin/bun
RUN ln -s /usr/local/bin/bun /usr/local/bin/bunx
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# System packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    postgresql-client \
    redis-tools \
    tree \
    lsof \
    jq \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# OpenCode verion
ARG OPENCODE_AI_VERSION=latest

# Install OpenCode
RUN npm install -g opencode-ai@${OPENCODE_AI_VERSION} \
    && npm cache clean --force

# Verify OpenCode installation
RUN opencode --version && \
    bun --version && \
    uv --version

# Switch to non-root user
USER vscode

# Setup AFT
RUN bunx --bun @cortexkit/aft setup

WORKDIR /workspace
CMD ["sleep", "infinity"]