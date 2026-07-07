#!/usr/bin/env bash
set -euo pipefail

# Looping entrypoint to run fetch_rates.py every 5 minutes.
# Pass OPENEXCHANGE_APP_ID or OPENEXCHANGE_APP_IDS and WP_UPLOADS via environment.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

trap "echo 'Stopping'; exit 0" SIGINT SIGTERM

while true; do
  echo "Running fetch at $(date -u +'%Y-%m-%d %H:%M:%S UTC')"
  python3 /app/fetch_rates.py || echo "fetch_rates failed"
  # sleep 5 minutes
  sleep 300
done
