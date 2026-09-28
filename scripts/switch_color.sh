#!/usr/bin/env bash
# Moves traffic to the other colour, which is what blue/green is for: no build,
# no image pull, about a second, and the version you are switching to has been
# running and warm since the deploy that replaced it.
#
#   scripts/switch_color.sh          # to whichever colour is not live
#   scripts/switch_color.sh blue     # to blue specifically
#
# This is the rollback. Redeploying an older commit also works but takes a build
# on the production host and leaves no warm copy of what you just left.
#
# It refuses rather than guesses: the target container must exist and answer
# /healthz before nginx is touched. A rollback fires when someone is already
# having a bad day, so the failure mode is "nothing changed, here is why".
set -euo pipefail

APP_NAME="${APP_NAME:-exchangehub}"
APP_DIR="${APP_DIR:-/home/deploy/apps/exchangehub}"
ASTRO_BLUE_PORT="${ASTRO_BLUE_PORT:-5003}"
ASTRO_GREEN_PORT="${ASTRO_GREEN_PORT:-5004}"
ACTIVE_FILE="${ACTIVE_FILE:-.deploy-active-color-astro}"
NGINX_UPSTREAM_CONF="${NGINX_UPSTREAM_CONF:-/etc/nginx/conf.d/${APP_NAME}-astro-upstream.conf}"
UPSTREAM_NAME="${UPSTREAM_NAME:-${APP_NAME}_astro_backend}"
HEALTH_PATH="${HEALTH_PATH:-/healthz}"

cd "$APP_DIR"

current_color="none"
if [[ -f "$ACTIVE_FILE" ]]; then
  current_color="$(cat "$ACTIVE_FILE")"
fi

target_color="${1:-}"
if [[ -z "$target_color" ]]; then
  if [[ "$current_color" == "blue" ]]; then
    target_color="green"
  else
    target_color="blue"
  fi
fi

if [[ "$target_color" != "blue" && "$target_color" != "green" ]]; then
  echo "Usage: $0 [blue|green]" >&2
  exit 2
fi

if [[ "$target_color" == "blue" ]]; then
  target_port="$ASTRO_BLUE_PORT"
  other_color="green"
  other_port="$ASTRO_GREEN_PORT"
else
  target_port="$ASTRO_GREEN_PORT"
  other_color="blue"
  other_port="$ASTRO_BLUE_PORT"
fi

target_container="${APP_NAME}-astro-${target_color}"
other_container="${APP_NAME}-astro-${other_color}"

if [[ "$target_color" == "$current_color" ]]; then
  echo "$target_color is already live. Nothing to do."
  exit 0
fi

if ! docker inspect "$target_container" >/dev/null 2>&1; then
  echo "$target_container does not exist, so there is nothing to switch to." >&2
  echo "Deploy normally instead -- that builds the idle colour and switches onto it." >&2
  exit 1
fi

if ! docker ps --filter "name=^/${target_container}$" --filter status=running --format '{{.Names}}' \
  | grep -q .; then
  echo "$target_container exists but is not running. Start it before switching:" >&2
  echo "  docker start $target_container" >&2
  exit 1
fi

# Proves the process answers, not that its data is good -- /healthz reads no
# rates. It was serving real traffic before the last deploy, which is the
# stronger evidence here.
if ! curl -fsS --max-time 10 "http://127.0.0.1:${target_port}${HEALTH_PATH}" >/dev/null; then
  echo "$target_container did not answer ${HEALTH_PATH} on 127.0.0.1:${target_port}." >&2
  docker logs --tail=40 "$target_container" >&2 || true
  exit 1
fi

echo "Switching from ${current_color} to ${target_color} (127.0.0.1:${target_port})..."

NEW_PORT="$target_port" OLD_PORT="$other_port" OLD_CONTAINER="$other_container" \
UPSTREAM_NAME="$UPSTREAM_NAME" NGINX_UPSTREAM_CONF="$NGINX_UPSTREAM_CONF" \
  scripts/write_upstream.sh

sudo nginx -t
sudo nginx -s reload

printf "%s" "$target_color" > "$ACTIVE_FILE"

# Nothing is stopped. The colour just left is now the backup and the way back,
# exactly as the colour just entered was a moment ago.
echo "Done. ${target_color} is live; ${other_color} is the backup on 127.0.0.1:${other_port}."
curl -fsS "http://127.0.0.1:${target_port}${HEALTH_PATH}" || true
echo
