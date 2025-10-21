FROM python:3.12-slim

# Avoid interactive prompts during package install
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:${PATH}"

# System deps for scientific Python, requests, OpenDartReader, PyGObject, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Copy project files
COPY pyproject.toml uv.lock* ./
COPY src/ ./src/
COPY scripts/ ./scripts/

# Install Python deps with uv (faster, reproducible)
RUN uv sync --frozen || uv sync

# Make scripts executable
RUN chmod +x /app/scripts/*.sh

CMD ["/app/scripts/entrypoint.sh"]
