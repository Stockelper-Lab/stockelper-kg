#!/usr/bin/env bash
# Run stockelper-kg with uv package manager

set -euo pipefail

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed"
    echo "Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Sync dependencies
echo "Syncing dependencies..."
uv sync

# Parse arguments
DATE_ST="${1:-$(date +%Y%m%d)}"
DATE_FN="${2:-$(date +%Y%m%d)}"

echo "Running stockelper-kg for dates: $DATE_ST to $DATE_FN"

# Run the application
uv run stockelper-kg --date_st "$DATE_ST" --date_fn "$DATE_FN"
