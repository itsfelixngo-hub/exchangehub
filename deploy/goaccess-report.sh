#!/bin/bash
# Turn the ratehubfx nginx access log into a self-contained HTML report.
#
#   sudo bash deploy/goaccess-report.sh                  # one-off report
#   sudo bash deploy/goaccess-report.sh --live           # keep it updating
#
# Install goaccess first:  sudo apt-get install -y goaccess
#
# The report is written to a local file. Do NOT serve it from a public vhost
# without a password -- it exposes visitor addresses and every URL requested.

set -euo pipefail

LOG="${LOG:-/var/log/nginx/ratehubfx.access.log}"
OUT="${OUT:-/var/www/goaccess/ratehubfx.html}"
LIVE=0
[ "${1:-}" = "--live" ] && LIVE=1

command -v goaccess >/dev/null || {
  echo "goaccess is not installed:  sudo apt-get install -y goaccess" >&2
  exit 1
}
[ -r "$LOG" ] || { echo "cannot read $LOG (run with sudo?)" >&2; exit 1; }

# Matches log_format ratehubfx in deploy/nginx-exchangehub.conf: goaccess's
# COMBINED spec plus the three key=value extras we append. %T picks up rt,
# which is what makes the response-time panels work.
LOG_FORMAT='%h %^[%d:%t %^] "%r" %s %b "%R" "%u" host=%^ rt=%T urt=%^'
DATE_FORMAT='%d/%b/%Y'
TIME_FORMAT='%H:%M:%S'

mkdir -p "$(dirname "$OUT")"

args=(
  "$LOG"
  --log-format="$LOG_FORMAT"
  --date-format="$DATE_FORMAT"
  --time-format="$TIME_FORMAT"
  --output="$OUT"
  --agent-list
  --real-os
  # Cloudflare answers most traffic, so origin logs are already a subset;
  # keeping 404s and bots visible is the point of looking at them at all.
  --http-method=yes
  --http-protocol=yes
)

if [ "$LIVE" = 1 ]; then
  echo "Live report -> $OUT (Ctrl-C to stop)"
  goaccess "${args[@]}" --real-time-html --daemonize
  echo "goaccess is running in the background; it serves updates on port 7890."
  echo "That port must NOT be exposed publicly."
else
  goaccess "${args[@]}"
  echo "Wrote $OUT"
  echo "Read it locally:  scp deploy@<vps>:$OUT ."
fi
