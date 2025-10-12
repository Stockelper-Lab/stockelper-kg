#!/usr/bin/env bash
set -euo pipefail

# Simple runner that ensures uv is available, creates a virtual env, installs deps, and runs the loader.

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

DATE_ST="${1:-}"
DATE_FN="${2:-}"

# Default to today's date when not provided
if [[ -z "${DATE_ST}" || -z "${DATE_FN}" ]]; then
  today=$(date +%Y%m%d)
  DATE_ST="${DATE_ST:-$today}"
  DATE_FN="${DATE_FN:-$today}"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found. Installing uv..."
  # Official installer (https://docs.astral.sh/uv/getting-started/installation/)
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# Ensure .env exists; if not, initialize from sample.env
if [[ ! -f .env && -f sample.env ]]; then
  echo ".env not found. Creating from sample.env..."
  cp sample.env .env
  # Set Neo4j defaults for local docker compose
  sed -i.bak 's#^NEO4J_URI *=.*#NEO4J_URI=bolt://localhost:7687#' .env || true
  sed -i.bak 's#^NEO4J_USER *=.*#NEO4J_USER=neo4j#' .env || true
  sed -i.bak 's#^NEO4J_PASSWORD *=.*#NEO4J_PASSWORD=password#' .env || true
  rm -f .env.bak
  echo ".env created. Please fill required API keys before running if needed."
fi

if [[ ! -f uv.lock ]]; then
  echo "Creating uv.lock (first-time resolution)..."
  uv lock || true
fi

echo "Syncing environment with uv..."
uv sync --frozen || uv sync

echo "Running loader: ${DATE_ST} -> ${DATE_FN}"
uv run python run_graphdb.py --date_st "${DATE_ST}" --date_fn "${DATE_FN}"
