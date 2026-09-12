#!/usr/bin/env bash
# Blue/green deploy for the Astro web app (astro-web/), which replaces the
# Flask app as the thing nginx serves.
#
# It reuses the machinery deploy_blue_green.sh already established rather than
# inventing a second one: the same two ports, the same active-colour file, the
# same /etc/nginx/conf.d/<app>-upstream.conf that the vhost includes. So no
# nginx config has to change to switch stacks — the upstream file just starts
# naming an Astro container.
#
# What this script deliberately does NOT touch:
#   - the mailserver, which the contact form still sends through
#   - the fetcher, which is what writes the rate JSON the Astro app reads
# Both stay owned by deploy_blue_green.sh. This script only replaces the web
# tier, and stops the Flask web containers once the Astro one is serving.
set -euo pipefail

APP_NAME="${APP_NAME:-exchangehub}"
APP_DIR="${APP_DIR:-/home/deploy/apps/exchangehub}"
BRANCH="${BRANCH:-main}"
IMAGE_TAG="${IMAGE_TAG:-}"
NETWORK_NAME="${NETWORK_NAME:-${APP_NAME}_net}"
BLUE_PORT="${BLUE_PORT:-5001}"
GREEN_PORT="${GREEN_PORT:-5002}"
ACTIVE_FILE="${ACTIVE_FILE:-.deploy-active-color}"
NGINX_UPSTREAM_CONF="${NGINX_UPSTREAM_CONF:-/etc/nginx/conf.d/${APP_NAME}-upstream.conf}"
HEALTH_PATH="${HEALTH_PATH:-/healthz}"
HEALTH_RETRIES="${HEALTH_RETRIES:-30}"
HEALTH_SLEEP="${HEALTH_SLEEP:-2}"
# The app listens on 4321 inside the container (astro-web/Dockerfile).
CONTAINER_PORT="${CONTAINER_PORT:-4321}"
UPLOADS_HOST_PATH="${UPLOADS_HOST_PATH:-${APP_DIR}/wp-content/uploads}"
# The Flask web containers this replaces. Removed after the switch, not before,
# so a failed deploy leaves the old stack serving. Same name and meaning as the
# variable deploy_blue_green.sh uses for the reverse direction.
SUPERSEDED_WEB_CONTAINERS="${SUPERSEDED_WEB_CONTAINERS:-${APP_NAME}-web-blue ${APP_NAME}-web-green ${APP_NAME}-web}"

# SWITCH_NGINX=false stages the new container on the idle port and stops there:
# nginx is not touched, the active-colour file is not rewritten, and nothing is
# removed. Visitors keep getting whatever is serving now.
#
# This exists because /healthz deliberately reads no rate data, so it cannot
# tell a working deploy from one that cannot reach R2. On this site R2 is the
# only source of rates (the production fetcher writes nowhere else), and a
# failed read falls back to local files that are empty -- which renders as a
# site with no rates rather than an error. The only way to catch that is to
# ask the staged container for a real page before sending it traffic.
#
# So: run once with SWITCH_NGINX=false, curl the port it prints, then run
# again with the default to flip.
SWITCH_NGINX="${SWITCH_NGINX:-true}"

cd "$APP_DIR"

if [[ "${SKIP_GIT_FETCH:-false}" != "true" ]]; then
  git fetch origin "$BRANCH"
  git reset --hard "origin/$BRANCH"
fi

if [[ -z "$IMAGE_TAG" ]]; then
  IMAGE_TAG="$(git rev-parse --short HEAD 2>/dev/null || date +%s)"
fi

if [[ ! -f .env ]]; then
  echo ".env is missing in $APP_DIR" >&2
  exit 1
fi

# Same reader deploy_blue_green.sh uses, so both scripts see one .env the same
# way. `cut -d= -f2-` keeps '=' inside values (base64 secrets, URLs).
env_value() {
  local key="$1"
  local default_value="$2"
  local value=""
  if [[ -f .env ]]; then
    value="$(grep "^${key}=" .env | tail -n1 | cut -d= -f2- || true)"
  fi
  printf "%s" "${value:-$default_value}"
}

# Absolute URLs (canonical, og:url, sitemap) cannot be derived from the request
# alone behind TLS termination -- see astro-web/src/lib/site.ts. Setting it
# here removes the guess entirely.
SITE_URL="$(env_value SITE_URL "https://$(env_value CF_ZONE_NAME ratehubfx.com)")"
CONTACT_SMTP_HOST_VALUE="$(env_value CONTACT_SMTP_HOST "${APP_NAME}-mailserver")"
CONTACT_SMTP_PORT_VALUE="$(env_value CONTACT_SMTP_PORT 587)"

current_color="none"
if [[ -f "$ACTIVE_FILE" ]]; then
  current_color="$(cat "$ACTIVE_FILE")"
fi

if [[ "$current_color" == "blue" ]]; then
  new_color="green"
  old_color="blue"
  new_port="$GREEN_PORT"
else
  new_color="blue"
  old_color="green"
  new_port="$BLUE_PORT"
fi

image="${APP_NAME}-astro:${IMAGE_TAG}"
new_container="${APP_NAME}-astro-${new_color}"
old_container="${APP_NAME}-astro-${old_color}"

docker network create "$NETWORK_NAME" >/dev/null 2>&1 || true

docker build --build-arg APP_BUILD="$IMAGE_TAG" -t "$image" ./astro-web
docker rm -f "$new_container" >/dev/null 2>&1 || true

# The rate JSON is mounted read-only: the fetcher owns those files, the web
# tier only reads them. With R2_ENABLED=true the mount is just the fallback
# path in astro-web/src/lib/rates.ts, which is why it is created if missing
# rather than required.
mkdir -p "$UPLOADS_HOST_PATH"

docker run -d \
  --name "$new_container" \
  --restart unless-stopped \
  --network "$NETWORK_NAME" \
  --env-file .env \
  -e NODE_ENV=production \
  -e HOST=0.0.0.0 \
  -e PORT="$CONTAINER_PORT" \
  -e SITE_URL="$SITE_URL" \
  -e APP_COLOR="$new_color" \
  -e WP_UPLOADS=/data/uploads \
  -e CONTACT_SMTP_HOST="$CONTACT_SMTP_HOST_VALUE" \
  -e CONTACT_SMTP_PORT="$CONTACT_SMTP_PORT_VALUE" \
  -v "${UPLOADS_HOST_PATH}:/data/uploads:ro" \
  -p "127.0.0.1:${new_port}:${CONTAINER_PORT}" \
  "$image"

for attempt in $(seq 1 "$HEALTH_RETRIES"); do
  if curl -fsS "http://127.0.0.1:${new_port}${HEALTH_PATH}" >/dev/null; then
    break
  fi
  if [[ "$attempt" == "$HEALTH_RETRIES" ]]; then
    echo "Health check failed for $new_container on port $new_port" >&2
    docker logs --tail=120 "$new_container" >&2 || true
    docker rm -f "$new_container" >/dev/null 2>&1 || true
    exit 1
  fi
  sleep "$HEALTH_SLEEP"
done

# /healthz deliberately touches no rate data, so it proves the process is up
# and nothing more. One real render fills the TTL caches in src/lib/rates.ts,
# which is the difference between a ~250ms and a ~10ms first visit. A single
# request is enough here: unlike gunicorn's several worker processes, the Node
# server is one process with one cache.
echo "Warming $new_container before switching traffic..."
if curl -fsS --max-time "${WARM_TIMEOUT:-60}" "http://127.0.0.1:${new_port}/" >/dev/null 2>&1; then
  echo "Warm-up completed."
else
  echo "Warm-up did not complete; continuing anyway." >&2
fi

if [[ "$SWITCH_NGINX" != "true" ]]; then
  cat <<EOF

Staged $image as $new_container on 127.0.0.1:${new_port}.
Nginx was NOT switched — visitors are still on whatever was serving before.

Check it against real data before flipping:

  curl -s 127.0.0.1:${new_port}/healthz
  curl -s 127.0.0.1:${new_port}/ | grep -c 'data-rates'
  curl -s 127.0.0.1:${new_port}/usd-vnd | grep -o '1 USD = [0-9.,]* VND'
  curl -s '127.0.0.1:${new_port}/api/rates?quote=VND' | head -c 200

An empty rate board means the container cannot read R2 — check the R2 keys in
.env before going further. When it looks right, deploy again with the default
SWITCH_NGINX=true to move nginx onto it.
EOF
  exit 0
fi

upstream_conf="upstream ${APP_NAME}_backend {
    server 127.0.0.1:${new_port};
}
"

if [[ -w "$(dirname "$NGINX_UPSTREAM_CONF")" ]]; then
  printf "%s" "$upstream_conf" > "$NGINX_UPSTREAM_CONF"
else
  printf "%s" "$upstream_conf" | sudo tee "$NGINX_UPSTREAM_CONF" >/dev/null
fi

sudo nginx -t
sudo nginx -s reload

printf "%s" "$new_color" > "$ACTIVE_FILE"

docker rm -f "$old_container" >/dev/null 2>&1 || true

# Traffic is on Astro now, so the Flask web containers are dead weight holding
# the other blue/green port. The fetcher and mailserver are left running.
for superseded in ${SUPERSEDED_WEB_CONTAINERS:-}; do
  if docker inspect "$superseded" >/dev/null 2>&1; then
    echo "Stopping superseded container: $superseded"
    docker rm -f "$superseded" >/dev/null 2>&1 || true
  fi
done

docker image prune -f >/dev/null 2>&1 || true

echo "Deployed $image to $new_container on 127.0.0.1:$new_port"
echo "Nginx now proxies to $new_color (Astro)."
