Project: Modular Exchange Rates and Game Content AI

Modules

- `modules/exchange_rates`: exchange-rate fetcher, Flask API/dev pages, WordPress plugin assets, and SEO pair-page renderer.
- `modules/game_content_ai`: AI-assisted rewrite tool for game detail content.

This project fetches exchange rates (e.g., VND ↔ USD) every 5 minutes and stores them in a local SQLite database. It provides a small Flask API for conversions and a frontend chart.

Quick start

1. Create a Python virtualenv and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Fetch rates once (use cron to run every 5 minutes):

```bash
python3 fetch_rates.py
```

3. Run the web server:

```bash
python3 app.py                       # dev
# production (what the container runs):
gunicorn --bind 0.0.0.0:5000 --workers 2 --worker-class gthread --threads 8 app:app
```

4. Open http://localhost:5000 in your browser to view the chart.

Game Content AI dev tool

- Open `http://localhost:5000/tools/game-content-ai`.
- Use dry-run mode without an API key.
- To call OpenAI, set `OPENAI_API_KEY` and optionally `OPENAI_MODEL` in `.env`.
- API endpoint:

```http
POST /api/game-content/rewrite
```

Scheduling every 5 minutes

- Using cron (example):

```cron
# run every 5 minutes
*/5 * * * * cd /path/to/repo && OPENEXCHANGE_APP_IDS=APP_ID_1,APP_ID_2,APP_ID_3 WP_UPLOADS=/var/www/html/wp-content/uploads /path/to/venv/bin/python3 fetch_rates.py >> /path/to/repo/fetch.log 2>&1
```

API endpoints

- `/api/latest?base=VND&target=USD` — latest rate
- `/api/history?base=VND&target=USD&hours=24` — last N hours
- `/api/convert?amount=100&base=VND&target=USD` — convert using latest rate

Performance

Pages are rendered server-side and served from an in-process cache, so a request
normally costs no rate-data work at all.

- A background warmer thread builds the rate model at startup and refreshes it
  every `PAGE_CACHE_SECONDS`, so no visitor ever pays for a cold render. The
  blue/green deploy also warms a new container before nginx points at it --
  `/healthz` answers without touching the rate model, so passing the health
  check is not proof the container is ready to serve a page quickly.
- When a cached page does expire, the stale copy is served immediately and the
  rebuild happens on a background thread (`PAGE_STALE_SECONDS` bounds how stale).
- Derived cross pairs (for example `EUR/JPY`) come from a single USD timeline
  built once per cache window instead of rescanning every stored entry per pair.
- Only pairs listed in `rate_pairs.json` are fetched from R2; misses are cached
  so derived pairs do not cost a round trip each.
- HTML/JSON responses are gzipped in-process and carry `Cache-Control`, so a CDN
  or `nginx` (see `deploy/nginx-exchangehub.conf`) can serve most traffic.
- Chart payloads are downsampled to `CHART_MAX_POINTS` and Chart.js / Google
  Translate load lazily rather than blocking first paint.

Tuning environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `PAGE_CACHE_SECONDS` | `60` | How long a rendered page stays fresh |
| `PAGE_STALE_SECONDS` | `900` | Extra window where a stale page is served while refreshing |
| `WARM_CACHE_ON_START` | `true` | Start the background warmer thread |
| `CHART_MAX_POINTS` | `400` | Points kept per chart series |
| `GZIP_LEVEL` / `GZIP_MIN_BYTES` | `6` / `1024` | Response compression |
| `STATIC_MAX_AGE` | `86400` | `Cache-Control` max-age for `/static` |
| `GUNICORN_WORKERS` / `GUNICORN_THREADS` | `2` / `8` | gunicorn sizing (compose and blue/green deploy) |

Notes

- The fetcher uses exchangerate.host free API.
- Adjust `modules/exchange_rates/rate_pairs.json` to set the exact pair files to store. Use `base_target` keys, for example:

```json
{
  "pairs": ["vnd_usd", "jpy_usd", "eur_usd"]
}
```

The API can derive cross pairs such as `VND → JPY` from those stored USD pairs.
- The fetcher writes one history file per pair, for example `rates/vnd_usd.json`, plus a lightweight `rates/index.json`. The storage target is controlled by `R2_ENABLED` and `LOCAL_STORAGE_ENABLED`.

Cloudflare R2 storage

- Generated rate files can be stored in Cloudflare R2, which is S3-compatible. Set these environment variables:

```bash
R2_ENABLED=true
LOCAL_STORAGE_ENABLED=false
R2_ACCOUNT_ID=YOUR_CLOUDFLARE_ACCOUNT_ID
R2_BUCKET=YOUR_BUCKET_NAME
R2_ACCESS_KEY_ID=YOUR_R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY=YOUR_R2_SECRET_ACCESS_KEY
# optional folder/prefix inside the bucket
R2_PREFIX=
```

- `R2_ENABLED=true` makes the fetcher and Flask app read/write R2.
- `LOCAL_STORAGE_ENABLED=false` disables writes to `wp-content/uploads`, which is the recommended production setting.
- `R2_PREFIX` is an optional folder prefix inside the bucket. Leave it blank if files should be written as `rates/index.json`, `rates/vnd_usd.json`, and `rates.html`. Do not set `R2_PREFIX=rates`, because the code already writes into the `rates/` path.

To upload existing local files in `wp-content/uploads/rates/` once:

```bash
python3 sync_rates_to_r2.py
```

- After `R2_ENABLED=true` is set, each normal fetch reads existing pair history from R2, writes the updated pair JSON files, `rates/index.json`, and `rates.html` back to R2, and the Flask app can read rates from R2 too.
- Keep `LOCAL_STORAGE_ENABLED=true` only if you explicitly want local test files under `wp-content/uploads`.

Deploy with R2

Use one active fetcher only. Local and production can both read R2, but only one environment should run the scheduled fetcher, otherwise both will call OpenExchangeRates and write to the same bucket.

1. Set production `.env`:

```bash
OPENEXCHANGE_APP_IDS=APP_ID_1,APP_ID_2,APP_ID_3
R2_ENABLED=true
LOCAL_STORAGE_ENABLED=false
R2_ACCOUNT_ID=YOUR_CLOUDFLARE_ACCOUNT_ID
R2_BUCKET=YOUR_BUCKET_NAME
R2_ACCESS_KEY_ID=YOUR_R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY=YOUR_R2_SECRET_ACCESS_KEY
R2_PREFIX=
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. If the bucket is empty, upload the current local history once:

```bash
python3 sync_rates_to_r2.py
```

4. Test one fetch:

```bash
python3 fetch_rates.py
```

Expected output includes paths such as:

```text
Wrote r2://YOUR_BUCKET/rates/index.json
Wrote r2://YOUR_BUCKET/rates.html
```

5. Run the fetcher in exactly one place.

Cron example:

```cron
*/5 * * * * cd /path/to/repo && /path/to/venv/bin/python3 fetch_rates.py >> /path/to/repo/fetch.log 2>&1
```

Docker Compose production:

```bash
docker-compose up --build -d
```

Local web-only after production fetcher is running:

```bash
docker-compose up --build -d web
docker-compose stop fetcher
```

Docker Compose names local containers as `exchangehub-web` and `exchangehub-fetcher`. If old containers from a previous project name still exist, remove them once:

```bash
docker rm -f alogweb_web_1 alogweb_fetcher_1 2>/dev/null || true
docker-compose up --build -d
```

If Docker Compose v1 fails with `KeyError: 'ContainerConfig'`, remove old compose containers and start again:

```bash
docker-compose down --remove-orphans
docker-compose up --build -d
```

GitHub Actions zero-downtime deploy

This repo includes `.github/workflows/deploy.yml` and `scripts/deploy_blue_green.sh` for blue/green VPS deploys. The deploy job runs directly on a self-hosted GitHub Actions runner installed on the production VPS; it does not use SSH.

Install one GitHub Actions self-hosted runner on the VPS and assign these labels:

```text
self-hosted, linux, exchangehub
```

The runner user must have access to the application directory and Docker, and must be able to run `sudo nginx -t` and `sudo nginx -s reload` without an interactive password. Register the runner at repository Settings → Actions → Runners, and keep it dedicated to this production repository.

Flow:

```text
git push origin main
-> CI verifies the commit on a GitHub-hosted runner
-> the production self-hosted runner fetches origin/main locally
-> writes production .env from GitHub Secrets
-> builds a new Docker image locally
-> starts the new web container on 127.0.0.1:5001 or 127.0.0.1:5002
-> checks /healthz
-> switches Nginx upstream and reloads Nginx
-> removes the old web container
-> restarts exactly one fetcher container
```

GitHub repository secrets:

```text
APP_DIR             # optional, defaults to /home/deploy/exchangehub
APP_NAME            # optional, defaults to exchangehub
BLUE_PORT           # optional, defaults to 5001
GREEN_PORT          # optional, defaults to 5002
NGINX_UPSTREAM_CONF # optional, defaults to /etc/nginx/conf.d/exchangehub-upstream.conf
PROD_ENV            # full production .env content
```

Example `PROD_ENV`:

```bash
OPENEXCHANGE_APP_IDS=APP_ID_1,APP_ID_2,APP_ID_3
R2_ENABLED=true
LOCAL_STORAGE_ENABLED=false
R2_ACCOUNT_ID=YOUR_CLOUDFLARE_ACCOUNT_ID
R2_BUCKET=YOUR_BUCKET_NAME
R2_ACCESS_KEY_ID=YOUR_R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY=YOUR_R2_SECRET_ACCESS_KEY
R2_PREFIX=
R2_READ_CACHE_SECONDS=300
PAGE_CACHE_SECONDS=300
GUNICORN_WORKERS=2
FLASK_SECRET_KEY=GENERATE_A_LONG_RANDOM_SECRET
SITE_CONTACT_EMAIL=contact@ratehubfx.com
CONTACT_FORWARD_TO=test.noreply909@gmail.com
CONTACT_FROM_EMAIL=contact@ratehubfx.com
CONTACT_SMTP_HOST=exchangehub-mailserver
CONTACT_SMTP_PORT=587
CONTACT_SMTP_USER=contact@ratehubfx.com
CONTACT_SMTP_PASSWORD=YOUR_SMTP_PASSWORD
CONTACT_SMTP_USE_TLS=true
CONTACT_SMTP_TLS_VERIFY=false
CONTACT_ROTATION_TOLERANCE=8
MAIL_HOSTNAME=mail
MAIL_DOMAIN=ratehubfx.com
MAIL_SSL_TYPE=self-signed
MAIL_POSTMASTER_ADDRESS=postmaster@ratehubfx.com
MAIL_POSTFIX_INET_PROTOCOLS=ipv4

# Optional but recommended when the VPS provider blocks outbound TCP/25.
# Example values depend on your SMTP relay provider.
MAIL_DEFAULT_RELAY_HOST=[smtp-relay.example.com]:587
MAIL_RELAY_USER=YOUR_RELAY_USERNAME
MAIL_RELAY_PASSWORD=YOUR_RELAY_PASSWORD
```

Built-in mailserver setup:

- The deploy script runs `ghcr.io/docker-mailserver/docker-mailserver`, a Postfix/Dovecot-based mailserver with DKIM/DMARC and spam filtering support.
- Point `mail.ratehubfx.com` A record to the VPS IP.
- Point `ratehubfx.com` MX record to `mail.ratehubfx.com`.
- Add SPF TXT on `ratehubfx.com`, for example `v=spf1 mx -all`.
- Add DMARC TXT, for example `_dmarc.ratehubfx.com TXT "v=DMARC1; p=quarantine; rua=mailto:test.noreply909@gmail.com"`.
- Open inbound ports `25`, `465`, `587`, `143`, and `993` on the VPS firewall and cloud firewall. Inbound `25` is required for receiving mail from other mail servers.
- Many VPS providers block outbound TCP/25, which causes logs like `connect to gmail-smtp-in.l.google.com[...]25: Connection timed out`. In that case, set an authenticated SMTP relay on port `587` with `MAIL_DEFAULT_RELAY_HOST`, `MAIL_RELAY_USER`, and `MAIL_RELAY_PASSWORD`.
- After deploy, confirm the relay was applied:

```bash
docker exec exchangehub-mailserver postconf relayhost smtp_sasl_auth_enable smtp_sasl_password_maps
docker exec exchangehub-mailserver env | grep -E 'DEFAULT_RELAY_HOST|RELAY_HOST|RELAY_PORT|RELAY_USER' | sed 's/RELAY_USER=.*/RELAY_USER=***hidden***/'
```

- Make sure reverse DNS/PTR for the VPS IP points to `mail.ratehubfx.com`; this is important for mail reputation.
- `MAIL_SSL_TYPE=self-signed` lets the mailserver boot without a pre-existing certificate. The deploy script creates the self-signed cert files under `docker-data/dms/config/ssl/`. Use `CONTACT_SMTP_TLS_VERIFY=false` with this mode. After a valid certificate exists at `/etc/letsencrypt/live/mail.ratehubfx.com`, change it to `MAIL_SSL_TYPE=letsencrypt` and `CONTACT_SMTP_TLS_VERIFY=true`.
- To import the Cloudflare DNS records automatically, set `CF_API_TOKEN` and `MAIL_SERVER_IP` in `.env`, then run:

```bash
python3 scripts/import_cloudflare_mail_dns.py --dry-run
python3 scripts/import_cloudflare_mail_dns.py
```

To import from a Cloudflare zone export file:

```bash
python3 scripts/import_cloudflare_mail_dns.py --zone-file deploy/ratehubfx.com.txt --dry-run
python3 scripts/import_cloudflare_mail_dns.py --zone-file deploy/ratehubfx.com.txt
```

- After first deploy, print the DKIM DNS record and add it to DNS:

```bash
docker exec exchangehub-mailserver cat /tmp/docker-mailserver/opendkim/keys/ratehubfx.com/mail.txt
```

Or import DKIM automatically after the file exists:

```bash
python3 scripts/import_cloudflare_mail_dns.py --dkim-file docker-data/dms/config/opendkim/keys/ratehubfx.com/mail.txt
```

- The contact form authenticates as `CONTACT_SMTP_USER` and forwards submissions to `CONTACT_FORWARD_TO`.

One-time VPS bootstrap:

```bash
sudo apt-get update
sudo apt-get install -y docker.io nginx git curl openssl
sudo usermod -aG docker deploy
sudo mkdir -p /home/deploy
sudo chown deploy:deploy /home/deploy
sudo -u deploy git clone git@github.com:YOUR_ORG/YOUR_REPO.git /home/deploy/exchangehub
sudo cp /home/deploy/exchangehub/deploy/nginx-exchangehub.conf /etc/nginx/sites-available/exchangehub.conf
sudo ln -s /etc/nginx/sites-available/exchangehub.conf /etc/nginx/sites-enabled/exchangehub.conf
echo 'upstream exchangehub_backend { server 127.0.0.1:5001; }' | sudo tee /etc/nginx/conf.d/exchangehub-upstream.conf
sudo nginx -t
sudo systemctl reload nginx
```

Edit `/etc/nginx/sites-available/exchangehub.conf` and replace `example.com` with your domain. If the deploy user cannot reload Nginx without a password, allow only these commands with sudo:

```text
deploy ALL=(root) NOPASSWD: /usr/sbin/nginx -t, /usr/sbin/nginx -s reload
```

Production traffic goes through Nginx to one active web container. The fetcher container is restarted as a single instance, so local and production do not both write R2.

SEO pair pages

- Python dev server also serves the same SEO-style routes at:

```text
http://127.0.0.1:5000/vnd-usd
http://127.0.0.1:5000/vnd-eur
```

- The WordPress plugin serves virtual SEO pages at:

```text
/vnd-usd
/usd-vnd
/vnd-eur
```

- Each page renders from the shared pair-page model: latest rate, converter table, chart data, statistics, FAQ, canonical URL, meta description, and JSON-LD FAQ schema.
- The reusable renderer lives in `wp-plugin-exchange/includes/exchange-rate-core.php`. WordPress is currently the first adapter; another platform can reuse the same model shape: `{base, target, history, latest, stats, amounts}`.
- Shortcode fallback for any WP page:

```text
[exchange_rate_pair base="VND" target="USD"]
```

Mono WP integration (recommended for SEO)

- In local-file mode, the fetcher writes per-pair JSON files and a pre-rendered partial `rates.html` into your WordPress uploads directory. With R2-only mode, those files are written to Cloudflare R2 instead.
- Use the theme snippet [wp_include_snippet.php](wp_include_snippet.php) to include the `rates.html` partial in your template.

Permissions and cron

- With `LOCAL_STORAGE_ENABLED=false`, the cron user does not need write access to `wp-content/uploads`.
- If local writes are enabled, ensure the user running the cron job can write to the uploads directory. Example cron to run every 5 minutes:

```cron
*/5 * * * * cd /path/to/repo && WP_UPLOADS=/var/www/html/wp-content/uploads /path/to/venv/bin/python3 fetch_rates.py >> /path/to/repo/fetch.log 2>&1
```

- Alternatively set `WP_UPLOADS` to a path inside the repo for testing (e.g., `wp-content/uploads`).

Atomic writes & caching

- `fetch_rates.py` writes to temporary files and `os.replace()` to avoid half-written files.
- For best performance and SEO, serve the static `rates.html` directly (Nginx will do this) and avoid parsing JSON on every page request. You can also pre-render `rates.html` so the HTML is returned to crawlers without JS.

Analytics tracking

- GA4 is installed with measurement ID `G-TN7DJB48VK`.
- Site-wide engagement events include `site_click`, `pair_link_click`, `outbound_link_click`, `control_change`, `section_view`, and `scroll_depth`.
- Conversion-style events include `contact_submit_success`, `form_submit_attempt`, `home_chart_series_loaded`, and `chart_tool_loaded`.
- Reliability and performance events include `api_request_error`, `api_request_exception`, `js_error`, `js_unhandled_rejection`, `web_vital_lcp`, `web_vital_cls`, and `web_vital_inp`.
- In GA4, mark `contact_submit_success` as a key event. Optionally mark `pair_link_click` and `chart_tool_loaded` if pair navigation and chart usage are important goals.

Next steps

- If you want, I can: (A) adjust `fetch_rates.py` to fetch more pairs, (B) add automatic pruning settings, or (C) create a small WP plugin wrapper around the snippet. Tell me which.
 
Docker (run both web and fetcher)

1. Build and run with docker-compose (example):

```bash
# set OPENEXCHANGE_APP_ID or OPENEXCHANGE_APP_IDS env, or put into an .env file
docker-compose up --build -d
```

2. The compose configuration runs two services:
- `web`: serves `app.py` on port 5000 as container `exchangehub-web`.
- `fetcher`: runs `fetch_rates.py` every 5 minutes as container `exchangehub-fetcher`. With `R2_ENABLED=true` and `LOCAL_STORAGE_ENABLED=false`, it reads and writes R2 only. With `LOCAL_STORAGE_ENABLED=true`, it also writes to `wp-content/uploads`.

3. Example to run with your real WP uploads path (host):

```bash
OPENEXCHANGE_APP_IDS=APP_ID_1,APP_ID_2,APP_ID_3 docker-compose up --build -d
```

4. To map uploads to your WordPress installation for local-file mode, edit `docker-compose.yml` volumes to mount the correct host path to `/app/wp-content/uploads`. This is not required for R2-only mode.

TLS with Cloudflare

DNS for `ratehubfx.com` and `www` is proxied through Cloudflare (orange
cloud), so visitors terminate TLS at the edge and Cloudflare re-connects to
the origin. `deploy/nginx-exchangehub.conf` is the reference server block for
that setup. It is **not** deployed automatically -- `deploy_blue_green.sh`
only rewrites `exchangehub-upstream.conf` -- so copy it to the server by hand.

This VPS hosts two sites. `alogweb` (`/etc/nginx/sites-enabled/alogweb`,
proxying to `127.0.0.1:8093`) was configured first and holds 80/443; this is
the second. They share both ports and are separated by SNI / `server_name`,
so each needs its own certificate. Because `alogweb` sorts before
`exchangehub.conf`, its blocks load first and are the implicit default
server: any request whose SNI matches neither site lands on alogweb.

1. Cloudflare dashboard -> SSL/TLS -> Origin Server -> **Create Certificate**,
   for this zone specifically. The certificate already in
   `/etc/ssl/cloudflare/` belongs to alogweb and covers only `alogweb.com`
   and `*.alogweb.com`, so it cannot be reused here. Save the new pair:

```bash
sudo install -d -m 0755 /etc/ssl/cloudflare
sudo install -m 0644 origin.pem /etc/ssl/cloudflare/ratehubfx.com.pem
sudo install -m 0600 origin.key /etc/ssl/cloudflare/ratehubfx.com.key
sudo curl -fsSLo /etc/ssl/cloudflare/origin-pull-ca.pem \
  https://developers.cloudflare.com/ssl/static/authenticated_origin_pull_ca.pem
```

2. Set Cloudflare SSL/TLS mode to **Full (strict)**. The `:80` block is left
   serving normally rather than redirecting, so a wrong mode here degrades
   instead of taking the site down; switch `:80` to a redirect only once
   Full (strict) is confirmed, since "Flexible" would loop it forever.

3. Optional, and off by default to match the alogweb vhost: **Authenticated
   Origin Pulls**. Turn it on in the dashboard (SSL/TLS -> Origin Server)
   *first*, then uncomment `ssl_client_certificate` and `ssl_verify_client`.
   Uncommenting them before the dashboard toggle answers every request 400.

4. Teach nginx which addresses are Cloudflare, so logs and `X-Real-IP` show
   the visitor rather than an edge node:

```bash
sudo bash deploy/cloudflare-realip.sh
```

5. Install and reload. Nothing in the deploy pipeline writes this file, so
   pushing to main will never update it -- it has to be copied by hand, once,
   and again whenever this repo's copy changes:

```bash
sudo cp /etc/nginx/sites-enabled/exchangehub.conf /root/exchangehub.conf.bak
sudo cp deploy/nginx-exchangehub.conf /etc/nginx/sites-enabled/exchangehub.conf
sudo nginx -t && sudo nginx -s reload      # restore the .bak if -t fails
```

Notes

- The upstream include at the top of the file stays commented out. Ubuntu's
  `nginx.conf` already globs `/etc/nginx/conf.d/*.conf`, so the upstream that
  `deploy_blue_green.sh` writes is loaded anyway; including it a second time
  is a fatal `duplicate upstream "exchangehub_backend"` at `nginx -t`.
- `listen 443 ssl http2;` works on every nginx since 1.9.5. On 1.25.1 and
  later it logs a deprecation notice; there, use `listen 443 ssl;` plus a
  separate `http2 on;`.
- `mail.ratehubfx.com` is deliberately **not** proxied through Cloudflare and
  does not go through nginx, so none of this affects mail.
- The HTTPS block is purely additive: the existing `:80` block is untouched,
  so installing it cannot take the site off the air. Both blocks proxy to the
  same upstream with the same headers.
- Until the `:443` block exists, TLS to the origin with SNI `ratehubfx.com`
  falls through to alogweb. Switching Cloudflare to "Full" before installing
  it would serve alogweb's content under ratehubfx.com; "Full (strict)" would
  fail with a 526. Install the block first, change the mode second.
- `http2` is a property of the listen socket rather than of a server block,
  so the value here must match what alogweb declares for the same port.
- `ssl_session_cache` uses a zone name of its own (`shared:ratehubfx:10m`);
  two vhosts declaring the same zone name with different sizes is a fatal
  error at `nginx -t`.
- The alogweb vhost needs no edits for these two to coexist. Only two things
  actually collide between vhosts, and neither is present: a second
  `default_server` on a port ("a duplicate default server for 0.0.0.0:443"),
  and a reused `ssl_session_cache` zone name at a different size. A differing
  `http2` flag on a shared listen socket is tolerated.
- Removing `/etc/nginx/sites-enabled/default` is safe. It holds the
  `default_server` for port 80; with it gone the first vhost loaded takes
  that role, and `alogweb` sorts before `exchangehub.conf`, so unmatched
  Host and SNI both land on alogweb exactly as they do today.
- Cloudflare does not cache HTML by default; the `Cache-Control` headers the
  app sets are ignored at the edge until a Cache Rule marks the site eligible
  for caching, so today every request still reaches the origin.
- To create the Origin Certificate through the API instead of the dashboard,
  an API token needs **Zone - SSL and Certificates - Edit** on the zone (the
  SSL counterpart to the `Zone:DNS:Edit` the DNS import script uses). Origin
  CA Keys still work but Cloudflare removes them on 2026-09-30.

Monitoring, security and edge caching

What already exists, and is mostly just unused:

- **Google Analytics** is embedded and reports 15 custom events, including
  Web Vitals (`web_vital_lcp`, `web_vital_cls`, `web_vital_inp`), `js_error`,
  `api_request_error` and `contact_submit_success`. Real-user performance data
  is already being collected; look under Reports -> Engagement -> Events.
- **Cloudflare Analytics** covers traffic, bandwidth, cache hit ratio and
  Security Events for free, since the zone is already proxied.

What the config adds:

- `log_format ratehubfx` keeps nginx's `combined` prefix and appends
  `host=`, `rt=` (what the visitor waited) and `urt=` (what the app took).
  The gap between the two is nginx plus network.
- `deploy/goaccess-report.sh` renders that log as an HTML report. It carries
  the matching goaccess `--log-format`, so it needs no arguments:

```bash
sudo apt-get install -y goaccess
sudo bash deploy/goaccess-report.sh            # one-off HTML report
sudo bash deploy/goaccess-report.sh --live     # keeps updating
```

  The report lists visitor addresses and every URL requested. Keep it behind a
  password, or read it locally over `scp`; do not serve it from a public vhost.

- Security headers on every response, errors included: HSTS,
  `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` and
  `Permissions-Policy`. **No CSP** -- the app inlines its scripts and styles
  and loads gtag, jsdelivr and Google Translate, so a policy that is both
  useful and non-breaking has to be worked out rather than guessed at.
- Rate limits on the two paths worth protecting: `/contact` at 10 r/m
  (it sends mail) and `/api/` at 300 r/m with a burst, since one page load
  fires five or six API calls. Both return 429 when tripped.

**Run `deploy/cloudflare-realip.sh` before relying on either.** Rate limits
key on the client address, and until nginx knows Cloudflare's ranges every
visitor shares a handful of edge addresses -- they would throttle each other,
and the logs would show Cloudflare rather than the visitor.

Cloudflare-side settings are applied by `scripts/cloudflare_setup.py`, which
reports by default and changes nothing without `--apply`:

```bash
python3 scripts/cloudflare_setup.py                        # report
python3 scripts/cloudflare_setup.py --cache-rule --apply   # edge-cache HTML
python3 scripts/cloudflare_setup.py --origin-pulls --apply
```

The cache rule matters most. Cloudflare does not cache HTML by default, so the
`Cache-Control` the app sends is ignored at the edge and every request still
reaches the origin; `cf-cache-status` reads `DYNAMIC`. The rule marks the zone
cacheable with `edge_ttl: respect_origin` -- the TTL stays defined in one
place, the app -- and excludes `/contact`, which carries a per-visitor token
and is served `no-store`.

Brotli is deliberately not configured at the origin: Cloudflare compresses to
the visitor itself, so it would only affect the Cloudflare-to-origin hop.

WP plugin (module) usage

- A simple plugin module is included at `wp-plugin-exchange/exchange-plugin.php`. To use it in your WordPress site, copy the `wp-plugin-exchange` folder into `wp-content/plugins/` and activate the plugin.
- Create posts of type "Exchange Pages" (in admin menu) for per-pair content. Use slugs like `vnd-usd` to match pair names.
- Place the shortcode `[exchange_rates_tabs]` on your homepage or any page to display the tabbed chart module. The module reads `rates.json` from the uploads folder to render charts.
