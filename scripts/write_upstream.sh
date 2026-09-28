#!/usr/bin/env bash
# Writes the one file that decides which container visitors reach:
# /etc/nginx/conf.d/<app>-astro-upstream.conf, which the vhost includes.
#
# Both deploy_astro.sh and switch_color.sh call this, so the file has one shape
# no matter which of them wrote it last. It does NOT reload nginx -- the caller
# does, after `nginx -t`, because what to do when the test fails differs.
#
# Inputs (all via the environment, since this is only ever called by the two
# scripts beside it):
#   NEW_PORT             the port traffic goes to
#   OLD_PORT             the other colour's port
#   OLD_CONTAINER        its container name, to check it is actually there
#   UPSTREAM_NAME        upstream block name, matched by the vhost's proxy_pass
#   NGINX_UPSTREAM_CONF  where to write
set -euo pipefail

: "${NEW_PORT:?NEW_PORT is required}"
: "${OLD_PORT:?OLD_PORT is required}"
: "${UPSTREAM_NAME:?UPSTREAM_NAME is required}"
: "${NGINX_UPSTREAM_CONF:?NGINX_UPSTREAM_CONF is required}"
OLD_CONTAINER="${OLD_CONTAINER:-}"

# The idle colour goes in as `backup`: nginx sends it nothing while the live
# server answers, and falls over to it when the live one refuses connections or
# times out. That turns a crashed or OOM-killed container from a site-wide 502
# into a request served by the previous version.
#
# Two consequences worth being explicit about:
#
#   - a failover serves the OLD build. For this site that is the right trade --
#     it renders rates read from R2, holds no session state and runs no
#     migrations, so an older build is a correct site, just not the newest one.
#     Do not copy this to a service where the two versions disagree about data.
#   - `max_fails=1 fail_timeout=10s` is nginx's default and is kept: one failure
#     parks the live server for 10s, and it is tried again after. So recovery
#     needs no intervention.
#
# A POST is not replayed: nginx does not pass a non-idempotent request to the
# next server once it has been sent, unless `non_idempotent` is listed in
# proxy_next_upstream -- and it deliberately is not (see
# deploy/nginx-ratehubfx-astro-proxy.conf). So a failover cannot send the
# contact form's mail twice.
#
# The backup line is omitted when that container does not exist, which is the
# case on the very first deploy of a pair. Naming a dead port would cost a
# pointless connection attempt on every failover.
backup_line=""
if [[ -n "$OLD_CONTAINER" ]] && docker inspect "$OLD_CONTAINER" >/dev/null 2>&1; then
  backup_line="
    server 127.0.0.1:${OLD_PORT} backup;"
fi

upstream_conf="upstream ${UPSTREAM_NAME} {
    server 127.0.0.1:${NEW_PORT};${backup_line}
}
"

if [[ -w "$(dirname "$NGINX_UPSTREAM_CONF")" ]]; then
  printf "%s" "$upstream_conf" > "$NGINX_UPSTREAM_CONF"
else
  printf "%s" "$upstream_conf" | sudo tee "$NGINX_UPSTREAM_CONF" >/dev/null
fi
