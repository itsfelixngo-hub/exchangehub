#!/usr/bin/env bash
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
GUNICORN_WORKERS="${GUNICORN_WORKERS:-}"
HEALTH_PATH="${HEALTH_PATH:-/healthz}"
HEALTH_RETRIES="${HEALTH_RETRIES:-30}"
HEALTH_SLEEP="${HEALTH_SLEEP:-2}"
STATE_DIR="${STATE_DIR:-${APP_DIR}/.deploy-state}"

cd "$APP_DIR"

git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

if [[ -z "$IMAGE_TAG" ]]; then
  IMAGE_TAG="$(git rev-parse --short HEAD 2>/dev/null || date +%s)"
fi

if [[ ! -f .env ]]; then
  echo ".env is missing in $APP_DIR" >&2
  exit 1
fi

if [[ -z "$GUNICORN_WORKERS" ]] && grep -q '^GUNICORN_WORKERS=' .env; then
  GUNICORN_WORKERS="$(grep -m1 '^GUNICORN_WORKERS=' .env | cut -d= -f2-)"
fi
GUNICORN_WORKERS="${GUNICORN_WORKERS:-2}"

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

image="${APP_NAME}:${IMAGE_TAG}"
new_container="${APP_NAME}-web-${new_color}"
old_container="${APP_NAME}-web-${old_color}"
fetcher_container="${APP_NAME}-fetcher"

docker network create "$NETWORK_NAME" >/dev/null 2>&1 || true
docker build -t "$image" .
docker rm -f "$new_container" >/dev/null 2>&1 || true

docker run -d \
  --name "$new_container" \
  --restart unless-stopped \
  --network "$NETWORK_NAME" \
  --env-file .env \
  -e FLASK_ENV=production \
  -p "127.0.0.1:${new_port}:5000" \
  "$image" \
  gunicorn -w "$GUNICORN_WORKERS" -b 0.0.0.0:5000 app:app

for attempt in $(seq 1 "$HEALTH_RETRIES"); do
  if curl -fsS "http://127.0.0.1:${new_port}${HEALTH_PATH}" >/dev/null; then
    break
  fi
  if [[ "$attempt" == "$HEALTH_RETRIES" ]]; then
    echo "Health check failed for $new_container on port $new_port" >&2
    docker logs --tail=120 "$new_container" >&2 || true
    exit 1
  fi
  sleep "$HEALTH_SLEEP"
done

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

docker rm -f "$fetcher_container" >/dev/null 2>&1 || true
mkdir -p "$STATE_DIR"
docker run -d \
  --name "$fetcher_container" \
  --restart unless-stopped \
  --network "$NETWORK_NAME" \
  --env-file .env \
  -e FLASK_ENV=production \
  -e OXR_APP_ID_STATE_FILE=/app/.deploy-state/openexchange_app_ids_state.json \
  -v "$STATE_DIR:/app/.deploy-state" \
  "$image" \
  /app/fetch_entrypoint.sh

docker image prune -f >/dev/null 2>&1 || true

echo "Deployed $image to $new_container on 127.0.0.1:$new_port"
echo "Nginx now proxies to $new_color. Fetcher is single-instance: $fetcher_container"
