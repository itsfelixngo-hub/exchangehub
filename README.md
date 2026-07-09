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
python3 app.py
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

This repo includes `.github/workflows/deploy.yml` and `scripts/deploy_blue_green.sh` for blue/green VPS deploys.

Flow:

```text
git push origin main
-> GitHub Actions SSHes into the VPS
-> writes production .env from GitHub Secrets
-> builds a new Docker image
-> starts the new web container on 127.0.0.1:5001 or 127.0.0.1:5002
-> checks /healthz
-> switches Nginx upstream and reloads Nginx
-> removes the old web container
-> restarts exactly one fetcher container
```

GitHub repository secrets:

```text
VPS_HOST
VPS_USER
VPS_SSH_KEY
VPS_SSH_PORT        # optional, defaults to 22
APP_DIR             # optional, defaults to /home/deploy/exchangehub
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
CONTACT_ROTATION_TOLERANCE=8
MAIL_HOSTNAME=mail
MAIL_DOMAIN=ratehubfx.com
MAIL_SSL_TYPE=self-signed
MAIL_POSTMASTER_ADDRESS=postmaster@ratehubfx.com
```

Built-in mailserver setup:

- The deploy script runs `ghcr.io/docker-mailserver/docker-mailserver`, a Postfix/Dovecot-based mailserver with DKIM/DMARC and spam filtering support.
- Point `mail.ratehubfx.com` A record to the VPS IP.
- Point `ratehubfx.com` MX record to `mail.ratehubfx.com`.
- Add SPF TXT on `ratehubfx.com`, for example `v=spf1 mx -all`.
- Add DMARC TXT, for example `_dmarc.ratehubfx.com TXT "v=DMARC1; p=quarantine; rua=mailto:test.noreply909@gmail.com"`.
- Open inbound ports `25`, `465`, `587`, `143`, and `993` on the VPS firewall and cloud firewall. Port `25` must not be blocked by the provider.
- Make sure reverse DNS/PTR for the VPS IP points to `mail.ratehubfx.com`; this is important for mail reputation.
- `MAIL_SSL_TYPE=self-signed` lets the mailserver boot without a pre-existing certificate. The deploy script creates the self-signed cert files under `docker-data/dms/config/ssl/`. After a valid certificate exists at `/etc/letsencrypt/live/mail.ratehubfx.com`, change it to `MAIL_SSL_TYPE=letsencrypt`.
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

WP plugin (module) usage

- A simple plugin module is included at `wp-plugin-exchange/exchange-plugin.php`. To use it in your WordPress site, copy the `wp-plugin-exchange` folder into `wp-content/plugins/` and activate the plugin.
- Create posts of type "Exchange Pages" (in admin menu) for per-pair content. Use slugs like `vnd-usd` to match pair names.
- Place the shortcode `[exchange_rates_tabs]` on your homepage or any page to display the tabbed chart module. The module reads `rates.json` from the uploads folder to render charts.
