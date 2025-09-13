#!/usr/bin/env bash
set -euo pipefail

# Controls whether to run ingestion automatically
RUN_GRAPHDB="${RUN_GRAPHDB:-false}"

# Optional date range; defaults to today's date if not provided
DATE_ST_INPUT="${DATE_ST:-}"
DATE_FN_INPUT="${DATE_FN:-}"

if [[ "${RUN_GRAPHDB}" == "true" ]]; then
  # Default to today's date when args are not provided
  today=$(date +%Y%m%d)
  DATE_ST="${DATE_ST_INPUT:-${today}}"
  DATE_FN="${DATE_FN_INPUT:-${today}}"
  echo "[entrypoint] Running graph load: ${DATE_ST} -> ${DATE_FN}"
  exec uv run python run_graphdb.py --date_st "${DATE_ST}" --date_fn "${DATE_FN}"
else
  echo "[entrypoint] RUN_GRAPHDB=false. Container is idle."
  exec bash -lc "tail -f /dev/null"
fi

