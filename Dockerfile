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

# Install Python deps with uv (faster, reproducible)
COPY pyproject.toml ./
RUN uv sync --frozen || uv sync

# Copy project files
COPY . .
RUN chmod +x /app/entrypoint.sh || true

CMD ["/app/entrypoint.sh"]
