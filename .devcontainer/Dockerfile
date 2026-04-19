# Base image
FROM mcr.microsoft.com/devcontainers/python:3.13-bookworm

# System packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \   
    redis-tools \         
    tree \                
    lsof \  
    jq \              
    && rm -rf /var/lib/apt/lists/*

# Node.js (required by OpenCode)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install OpenCode
RUN npm install -g opencode-ai

# Verify OpenCode installation
RUN opencode --version

# Package manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

USER vscode
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/home/vscode/.local/bin:${PATH}"

WORKDIR /workspace
CMD ["sleep", "infinity"]