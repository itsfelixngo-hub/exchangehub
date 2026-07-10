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
MAIL_HEALTH_RETRIES="${MAIL_HEALTH_RETRIES:-12}"
MAIL_HEALTH_SLEEP="${MAIL_HEALTH_SLEEP:-5}"
STATE_DIR="${STATE_DIR:-${APP_DIR}/.deploy-state}"
MAILSERVER_IMAGE="${MAILSERVER_IMAGE:-ghcr.io/docker-mailserver/docker-mailserver:latest}"
MAILSERVER_CONTAINER="${MAILSERVER_CONTAINER:-${APP_NAME}-mailserver}"
MAIL_DATA_ROOT="${MAIL_DATA_ROOT:-${APP_DIR}/docker-data/dms}"

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
  GUNICORN_WORKERS="$(grep '^GUNICORN_WORKERS=' .env | tail -n1 | cut -d= -f2-)"
fi
GUNICORN_WORKERS="${GUNICORN_WORKERS:-2}"

env_value() {
  local key="$1"
  local default_value="$2"
  local value=""
  if [[ -f .env ]]; then
    value="$(grep "^${key}=" .env | tail -n1 | cut -d= -f2- || true)"
  fi
  printf "%s" "${value:-$default_value}"
}

MAIL_HOSTNAME="$(env_value MAIL_HOSTNAME mail)"
MAIL_DOMAIN="$(env_value MAIL_DOMAIN ratehubfx.com)"
MAIL_FQDN="${MAIL_HOSTNAME}.${MAIL_DOMAIN}"
MAIL_PORT_SMTP="$(env_value MAIL_PORT_SMTP 25)"
MAIL_PORT_SUBMISSION="$(env_value MAIL_PORT_SUBMISSION 587)"
MAIL_PORT_SUBMISSIONS="$(env_value MAIL_PORT_SUBMISSIONS 465)"
MAIL_PORT_IMAP="$(env_value MAIL_PORT_IMAP 143)"
MAIL_PORT_IMAPS="$(env_value MAIL_PORT_IMAPS 993)"
MAIL_ENABLE_SPAMASSASSIN="$(env_value MAIL_ENABLE_SPAMASSASSIN 1)"
MAIL_ENABLE_CLAMAV="$(env_value MAIL_ENABLE_CLAMAV 0)"
MAIL_ENABLE_FAIL2BAN="$(env_value MAIL_ENABLE_FAIL2BAN 1)"
MAIL_ENABLE_POSTGREY="$(env_value MAIL_ENABLE_POSTGREY 0)"
MAIL_SSL_TYPE="$(env_value MAIL_SSL_TYPE self-signed)"
MAIL_POSTMASTER_ADDRESS="$(env_value MAIL_POSTMASTER_ADDRESS postmaster@ratehubfx.com)"
MAIL_PERMIT_DOCKER="$(env_value MAIL_PERMIT_DOCKER none)"
MAIL_DEFAULT_RELAY_HOST="$(env_value MAIL_DEFAULT_RELAY_HOST "")"
MAIL_RELAY_HOST="$(env_value MAIL_RELAY_HOST "")"
MAIL_RELAY_PORT="$(env_value MAIL_RELAY_PORT "")"
MAIL_RELAY_USER="$(env_value MAIL_RELAY_USER "")"
MAIL_RELAY_PASSWORD="$(env_value MAIL_RELAY_PASSWORD "")"
MAIL_POSTFIX_INET_PROTOCOLS="$(env_value MAIL_POSTFIX_INET_PROTOCOLS ipv4)"
CONTACT_SMTP_USER_VALUE="$(env_value CONTACT_SMTP_USER "")"
CONTACT_SMTP_PASSWORD_VALUE="$(env_value CONTACT_SMTP_PASSWORD "")"
CONTACT_SMTP_HOST_VALUE="$(env_value CONTACT_SMTP_HOST "$MAILSERVER_CONTAINER")"
CONTACT_SMTP_PORT_VALUE="$(env_value CONTACT_SMTP_PORT 587)"
CONTACT_FORWARD_TO_VALUE="$(env_value CONTACT_FORWARD_TO "")"

mail_relay_args=()
if [[ -n "$MAIL_DEFAULT_RELAY_HOST" ]]; then
  mail_relay_args+=(-e "DEFAULT_RELAY_HOST=$MAIL_DEFAULT_RELAY_HOST")
fi
if [[ -n "$MAIL_RELAY_HOST" ]]; then
  mail_relay_args+=(-e "RELAY_HOST=$MAIL_RELAY_HOST")
fi
if [[ -n "$MAIL_RELAY_PORT" ]]; then
  mail_relay_args+=(-e "RELAY_PORT=$MAIL_RELAY_PORT")
fi
if [[ -n "$MAIL_RELAY_USER" ]]; then
  mail_relay_args+=(-e "RELAY_USER=$MAIL_RELAY_USER")
fi
if [[ -n "$MAIL_RELAY_PASSWORD" ]]; then
  mail_relay_args+=(-e "RELAY_PASSWORD=$MAIL_RELAY_PASSWORD")
fi

if [[ -n "$MAIL_DEFAULT_RELAY_HOST" || -n "$MAIL_RELAY_HOST" ]]; then
  echo "Mail relay enabled: ${MAIL_DEFAULT_RELAY_HOST:-${MAIL_RELAY_HOST}:${MAIL_RELAY_PORT:-25}}"
else
  echo "Mail relay disabled: outbound delivery will use recipient MX on TCP/25."
fi

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

mkdir -p \
  "$MAIL_DATA_ROOT/mail-data" \
  "$MAIL_DATA_ROOT/mail-state" \
  "$MAIL_DATA_ROOT/mail-logs" \
  "$MAIL_DATA_ROOT/config"

if [[ "$MAIL_SSL_TYPE" == "self-signed" ]]; then
  mkdir -p "$MAIL_DATA_ROOT/config/ssl/demoCA"
  if [[ ! -f "$MAIL_DATA_ROOT/config/ssl/${MAIL_FQDN}-key.pem" || ! -f "$MAIL_DATA_ROOT/config/ssl/${MAIL_FQDN}-cert.pem" ]]; then
    openssl req -x509 -newkey rsa:4096 -sha256 -days 3650 -nodes \
      -keyout "$MAIL_DATA_ROOT/config/ssl/${MAIL_FQDN}-key.pem" \
      -out "$MAIL_DATA_ROOT/config/ssl/${MAIL_FQDN}-cert.pem" \
      -subj "/CN=${MAIL_FQDN}" \
      -addext "subjectAltName=DNS:${MAIL_FQDN},DNS:${MAIL_DOMAIN}" >/dev/null 2>&1
  fi
  cp "$MAIL_DATA_ROOT/config/ssl/${MAIL_FQDN}-cert.pem" "$MAIL_DATA_ROOT/config/ssl/demoCA/cacert.pem"
fi

docker pull "$MAILSERVER_IMAGE" >/dev/null
if [[ -n "$CONTACT_SMTP_USER_VALUE" && -n "$CONTACT_SMTP_PASSWORD_VALUE" ]]; then
  if ! docker run --rm \
    -v "$MAIL_DATA_ROOT/config:/tmp/docker-mailserver" \
    "$MAILSERVER_IMAGE" \
    setup email add "$CONTACT_SMTP_USER_VALUE" "$CONTACT_SMTP_PASSWORD_VALUE" >/dev/null 2>&1; then
    docker run --rm \
      -v "$MAIL_DATA_ROOT/config:/tmp/docker-mailserver" \
      "$MAILSERVER_IMAGE" \
      setup email update "$CONTACT_SMTP_USER_VALUE" "$CONTACT_SMTP_PASSWORD_VALUE" >/dev/null 2>&1
  fi
  if [[ -n "$CONTACT_FORWARD_TO_VALUE" ]]; then
    docker run --rm \
      -v "$MAIL_DATA_ROOT/config:/tmp/docker-mailserver" \
      "$MAILSERVER_IMAGE" \
      setup alias add "$CONTACT_SMTP_USER_VALUE" "$CONTACT_FORWARD_TO_VALUE" >/dev/null 2>&1 || true
  fi
  docker run --rm \
    -v "$MAIL_DATA_ROOT/config:/tmp/docker-mailserver" \
    "$MAILSERVER_IMAGE" \
    setup config dkim domain "$MAIL_DOMAIN" >/dev/null 2>&1 || true
fi

docker rm -f "$MAILSERVER_CONTAINER" >/dev/null 2>&1 || true
docker run -d \
  --name "$MAILSERVER_CONTAINER" \
  --restart unless-stopped \
  --network "$NETWORK_NAME" \
  --hostname "$MAIL_FQDN" \
  -e OVERRIDE_HOSTNAME="$MAIL_FQDN" \
  -e ENABLE_SPAMASSASSIN="$MAIL_ENABLE_SPAMASSASSIN" \
  -e ENABLE_CLAMAV="$MAIL_ENABLE_CLAMAV" \
  -e ENABLE_FAIL2BAN="$MAIL_ENABLE_FAIL2BAN" \
  -e ENABLE_POSTGREY="$MAIL_ENABLE_POSTGREY" \
  -e SSL_TYPE="$MAIL_SSL_TYPE" \
  -e POSTMASTER_ADDRESS="$MAIL_POSTMASTER_ADDRESS" \
  -e PERMIT_DOCKER="$MAIL_PERMIT_DOCKER" \
  -e POSTFIX_INET_PROTOCOLS="$MAIL_POSTFIX_INET_PROTOCOLS" \
  "${mail_relay_args[@]}" \
  -e ONE_DIR=1 \
  -e DMS_DEBUG=0 \
  -p "${MAIL_PORT_SMTP}:25" \
  -p "${MAIL_PORT_SUBMISSION}:587" \
  -p "${MAIL_PORT_SUBMISSIONS}:465" \
  -p "${MAIL_PORT_IMAP}:143" \
  -p "${MAIL_PORT_IMAPS}:993" \
  -v "$MAIL_DATA_ROOT/mail-data:/var/mail" \
  -v "$MAIL_DATA_ROOT/mail-state:/var/mail-state" \
  -v "$MAIL_DATA_ROOT/mail-logs:/var/log/mail" \
  -v "$MAIL_DATA_ROOT/config:/tmp/docker-mailserver" \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/letsencrypt:/etc/letsencrypt:ro \
  --cap-add NET_ADMIN \
  "$MAILSERVER_IMAGE"

for attempt in $(seq 1 "$MAIL_HEALTH_RETRIES"); do
  mail_status="$(docker inspect -f '{{.State.Status}} {{.State.Restarting}}' "$MAILSERVER_CONTAINER" 2>/dev/null || true)"
  if [[ "$mail_status" == "running false" ]]; then
    break
  fi
  if [[ "$attempt" == "$MAIL_HEALTH_RETRIES" ]]; then
    echo "Mailserver failed to stay running. Container state: ${mail_status:-unknown}" >&2
    docker logs --tail=160 "$MAILSERVER_CONTAINER" >&2 || true
    exit 1
  fi
  sleep "$MAIL_HEALTH_SLEEP"
done

docker build -t "$image" .
docker rm -f "$new_container" >/dev/null 2>&1 || true

docker run -d \
  --name "$new_container" \
  --restart unless-stopped \
  --network "$NETWORK_NAME" \
  --env-file .env \
  -e FLASK_ENV=production \
  -e CONTACT_SMTP_HOST="$CONTACT_SMTP_HOST_VALUE" \
  -e CONTACT_SMTP_PORT="$CONTACT_SMTP_PORT_VALUE" \
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
