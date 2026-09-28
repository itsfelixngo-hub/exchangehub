#!/usr/bin/env bash
# Blue/green deploy for the Astro site at the repo root — the web tier, and
# only the web tier.
#
# What this script deliberately does NOT touch:
#   - the mailserver, which the contact form sends through
#   - the fetcher, which writes the rate JSON the site reads
# Those are scripts/deploy_fetcher_mail.sh, which the Deploy workflow runs only
# when DEPLOY_FETCHER_MAIL is set: both are long-lived single containers, and
# recreating the fetcher costs an extra OpenExchangeRates call for nothing.
set -euo pipefail

APP_NAME="${APP_NAME:-exchangehub}"
APP_DIR="${APP_DIR:-/home/deploy/apps/exchangehub}"
BRANCH="${BRANCH:-main}"
IMAGE_TAG="${IMAGE_TAG:-}"
NETWORK_NAME="${NETWORK_NAME:-${APP_NAME}_net}"
# 5003/5004 rather than the 5001/5002 the Flask app used, and its own
# active-colour and upstream files: the separation is what let the two stacks
# run at once during the cutover. Flask is gone, but the names stay -- renaming
# them now would mean editing the vhost, the upstream file and the secrets.
ASTRO_BLUE_PORT="${ASTRO_BLUE_PORT:-5003}"
ASTRO_GREEN_PORT="${ASTRO_GREEN_PORT:-5004}"
ACTIVE_FILE="${ACTIVE_FILE:-.deploy-active-color-astro}"
NGINX_UPSTREAM_CONF="${NGINX_UPSTREAM_CONF:-/etc/nginx/conf.d/${APP_NAME}-astro-upstream.conf}"
# Must match the `proxy_pass` in deploy/nginx-ratehubfx-astro-proxy.conf.
UPSTREAM_NAME="${UPSTREAM_NAME:-${APP_NAME}_astro_backend}"
HEALTH_PATH="${HEALTH_PATH:-/healthz}"
HEALTH_RETRIES="${HEALTH_RETRIES:-30}"
HEALTH_SLEEP="${HEALTH_SLEEP:-2}"
# The app listens on 5003 inside the container (Dockerfile, astro.config.mjs):
# one port for this project everywhere. The blue container therefore publishes
# 5003 -> 5003 and the green one 5004 -> 5003 — the host port is what
# alternates, the container port never moves.
CONTAINER_PORT="${CONTAINER_PORT:-5003}"
UPLOADS_HOST_PATH="${UPLOADS_HOST_PATH:-${APP_DIR}/wp-content/uploads}"

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

# Both colours stay running. This is what makes the switch free of dropped
# requests, and it replaces the timed drain this script used to do.
#
# The problem with removing the superseded container: `nginx -s reload` is
# graceful about accepting connections, but the old worker processes finish the
# requests they already accepted while still holding the OLD configuration --
# so they are still proxying to the old container. Killing it when reload
# returns cuts those responses. A `sleep` covered the common case and nothing
# more, since nginx allows a request to run for proxy_read_timeout (60s).
#
# Not killing it at all removes the race instead of narrowing it. The old
# version keeps serving until its own workers are done, on its own port, and is
# then simply idle. It is replaced at the START of the next deploy, by which
# time no traffic has reached it for a full deploy cycle.
#
# Two things fall out of that, both wanted:
#   - the idle colour is a warm rollback target. scripts/switch_color.sh moves
#     traffic back onto it in about a second, with no rebuild.
#   - it can be the upstream's `backup`, so a crash of the live container fails
#     over instead of returning 502.
#
# The cost is one extra idle Node process (~100MB) on the box for as long as
# nothing is deployed.

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

# Same reader deploy_fetcher_mail.sh uses, so both scripts see one .env the same
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
# alone behind TLS termination -- see src/lib/site.ts. Setting it
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
  new_port="$ASTRO_GREEN_PORT"
  old_port="$ASTRO_BLUE_PORT"
else
  new_color="blue"
  old_color="green"
  new_port="$ASTRO_BLUE_PORT"
  old_port="$ASTRO_GREEN_PORT"
fi

image="${APP_NAME}-astro:${IMAGE_TAG}"
new_container="${APP_NAME}-astro-${new_color}"
old_container="${APP_NAME}-astro-${old_color}"

docker network create "$NETWORK_NAME" >/dev/null 2>&1 || true

docker build --build-arg APP_BUILD="$IMAGE_TAG" -t "$image" .

# Removing the idle colour is safe where removing the live one was not: no
# request has been routed to it since the previous switch. It can only be
# reached as the upstream's `backup`, and only while the live container is
# failing -- in which case the site has a bigger problem than this window.
docker rm -f "$new_container" >/dev/null 2>&1 || true

# The rate JSON is mounted read-only: the fetcher owns those files, the web
# tier only reads them. With R2_ENABLED=true the mount is just the fallback
# path in src/lib/rates.ts, which is why it is created if missing
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

# scripts/write_upstream.sh owns the file, so a deploy and a rollback cannot
# disagree about its shape.
NEW_PORT="$new_port" OLD_PORT="$old_port" OLD_CONTAINER="$old_container" \
UPSTREAM_NAME="$UPSTREAM_NAME" NGINX_UPSTREAM_CONF="$NGINX_UPSTREAM_CONF" \
  scripts/write_upstream.sh

sudo nginx -t
sudo nginx -s reload

printf "%s" "$new_color" > "$ACTIVE_FILE"

# The old container is deliberately left running -- see the comment on the
# colours above. It is the warm rollback target and the upstream's backup, and
# the next deploy is what replaces it.

# Only dangling images, so the two tagged images the two containers run are
# never candidates.
docker image prune -f >/dev/null 2>&1 || true

echo "Deployed $image to $new_container on 127.0.0.1:$new_port"
echo "Nginx now proxies to $new_color (Astro)."
if docker inspect "$old_container" >/dev/null 2>&1; then
  echo "$old_color is still up on 127.0.0.1:$old_port as the backup and the rollback target."
  echo "  roll back with: scripts/switch_color.sh $old_color"
fi
