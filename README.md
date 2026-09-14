Project: ExchangeHub

Two parts, one repository

- `src/`, `public/`: the Astro site — the pages nginx serves. Built by `Dockerfile`.
- `modules/exchange_rates`: the rate fetcher and its R2 storage layer. Built by `Dockerfile.fetcher`. This is all the Python that is left; the Flask app, its WordPress plugin and the game-content tool were removed when the Astro site replaced them.

The fetcher pulls exchange rates (e.g., VND ↔ USD) every 5 minutes and writes them to Cloudflare R2. The site reads them from there and renders the converter, the rate board and the per-pair pages. The two never talk to each other directly — R2 is the whole interface, and the site only ever reads.

Quick start

Node 22.12 or newer; Astro 7 refuses to start on Node 20.

```bash
npm ci
npm run dev          # http://localhost:5003
```

`.env` at the repo root is read automatically (see `src/lib/env.ts`), so a local
run against the production R2 bucket needs no extra flags. Other scripts:

```bash
npm run check        # astro check — typecheck .astro and .ts
npm run build        # dist/ — the Node adapter's standalone server
npm run smoke        # boots dist/ against fixture rates and asserts the routes
npm start            # run the built server
```

To run the fetcher locally instead — only ever one fetcher anywhere, see
"Deploy with R2":

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 fetch_rates.py
```

Scheduling every 5 minutes

- Using cron (example):

```cron
# run every 5 minutes
*/5 * * * * cd /path/to/repo && OPENEXCHANGE_APP_IDS=APP_ID_1,APP_ID_2,APP_ID_3 WP_UPLOADS=/var/www/html/wp-content/uploads /path/to/venv/bin/python3 fetch_rates.py >> /path/to/repo/fetch.log 2>&1
```

Routes the site serves

| Route | Purpose |
| --- | --- |
| `/` | converter, rate board, hero chart |
| `/<code>` | currency hub, e.g. `/vnd` — every pair under one currency |
| `/<base>-<target>` | pair page, e.g. `/usd-vnd` — rate, converter, chart, statistics, FAQ |
| `/analysis` | the header's Analysis tab: every currency with its 24H card |
| `/chart` | chart index across every tracked pair |
| `/about`, `/contact`, `/privacy-policy`, `/terms`, `/disclaimer` | static copy from `src/lib/info.ts` |
| `/api/rates?quote=VND` | rate-board rows for one quote currency |
| `/api/hero?base=USD&target=VND` | hero chart series for one pair |
| `/healthz` | liveness plus which build answered; reads no rate data |
| `/robots.txt` | points at the sitemap index |
| `/sitemap.xml` | index over `/sitemap-pages.xml`, `/sitemap-currencies.xml` and one `/sitemap-pairs-<code>.xml` per hub |

`/vnd` and `/vnd-usd` sit in the same URL segment, so one dynamic route
(`src/pages/[slug].astro`) serves both and tells them apart by shape. The URLs
stay flat on purpose — the hierarchy is expressed by the breadcrumbs and the
sitemap index, not by nesting `/vnd/usd`.

Wrong or unknown pairs 404; `/eur-usd/`, `/EUR-USD`, `/eur_usd` and
`/exchange/eur-usd` all redirect to `/eur-usd`, so one page has one URL.

Performance

Every page is rendered per request by the Node adapter — there is no page
cache. What is cached is the rate data underneath, in-process and shared by
every request the container serves.

- `memoByTtl` in `src/lib/rates.ts` caches the *in-flight promise*, not the
  resolved value, so several requests arriving on a cold cache share one R2
  read instead of each starting their own. A rejection is dropped so the next
  caller retries rather than inheriting the failure for the whole window.
- The cache window is `R2_READ_CACHE_SECONDS`, on the same clock as the data:
  a cached answer can never be staler than the entries behind it.
- Derived cross pairs (for example `EUR/JPY`) come from a single USD timeline
  built once per window instead of rescanning every stored entry per pair.
  Misses are cached too, since most menu pairs have no stored file of their own.
- `PAIR_CONCURRENCY` bounds how many pair histories load at once: wide enough
  to hide R2 latency, narrow enough that only a handful of decoded histories
  are live at the same time.
- The blue/green deploy warms a new container with one real page request before
  nginx points at it. `/healthz` deliberately touches no rate data, so passing
  it is not proof the container can serve a page quickly — or at all.
- Chart payloads are downsampled to `CHART_MAX_POINTS` / `PAIR_CHART_MAX_POINTS`.
- gzip and `Cache-Control` are nginx's job here, not the app's — see
  `deploy/nginx-exchangehub-astro.conf`, which also caches `/_astro/` and the
  flag images for a year.

Tuning environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `R2_READ_CACHE_SECONDS` | `60` | How long rate data stays fresh in process |
| `PAIR_CONCURRENCY` | `6` | Pair histories loaded at once |
| `CHART_MAX_POINTS` | `400` | Points kept per home-page chart series |
| `PAIR_CHART_MAX_POINTS` | `600` | Points kept per pair-page series |
| `NOINDEX_LONGTAIL_PAIRS` | unset | Keep non-menu pairs out of the index — see "Ad network review" |
| `SITE_URL` | unset | Origin for canonical, og:url and sitemap; set by the deploy script |

Notes

- The fetcher reads OpenExchangeRates (`OPENEXCHANGE_APP_IDS`, rotated when one
  key hits its quota) and falls back to exchangerate.host for a single pair.
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

- `R2_ENABLED=true` makes the fetcher write to R2 and the site read from it.
- `LOCAL_STORAGE_ENABLED=false` disables writes to `wp-content/uploads`, which is the recommended production setting.
- `R2_PREFIX` is an optional folder prefix inside the bucket. Leave it blank if files should be written as `rates/index.json`, `rates/vnd_usd.json`, and `rates.html`. Do not set `R2_PREFIX=rates`, because the code already writes into the `rates/` path.

- After `R2_ENABLED=true` is set, each normal fetch reads existing pair history from R2, writes the updated pair JSON files and `rates/index.json` back to R2, and the site reads them from R2. There is no separate upload step: one run of `fetch_rates.py` against an empty bucket populates it.
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

3. Test one fetch — this also populates an empty bucket:

```bash
python3 fetch_rates.py
```

Expected output includes paths such as:

```text
Wrote r2://YOUR_BUCKET/rates/index.json
Wrote r2://YOUR_BUCKET/rates.html
```

4. Run the fetcher in exactly one place.

Cron example:

```cron
*/5 * * * * cd /path/to/repo && /path/to/venv/bin/python3 fetch_rates.py >> /path/to/repo/fetch.log 2>&1
```

Everything at once, locally:

```bash
docker compose up --build -d
```

Site only, when the production fetcher is already running — which is the normal
local setup, since two fetchers would both call OpenExchangeRates and write the
same bucket:

```bash
docker compose up --build -d astro
```

Compose defines three services: `astro` (the site, container
`exchangehub-astro`, port 5003), `fetcher` (container `exchangehub-fetcher`)
and `mailserver`. Note that production does **not** use compose — the deploy
scripts run `docker run` directly; see "GitHub Actions zero-downtime deploy".

If Docker Compose v1 fails with `KeyError: 'ContainerConfig'`, remove old compose containers and start again:

```bash
docker compose down --remove-orphans
docker compose up --build -d
```

GitHub Actions zero-downtime deploy

This repo includes `.github/workflows/deploy.yml`, `scripts/deploy_astro.sh` (the site, blue/green) and `scripts/deploy_fetcher_mail.sh` (the fetcher and the mailserver) for VPS deploys. The deploy job runs directly on a self-hosted GitHub Actions runner installed on the production VPS; it does not use SSH.

Install one GitHub Actions self-hosted runner on the VPS and assign these labels:

```text
self-hosted, linux, exchangehub
```

The runner user must have access to the application directory and Docker, and must be able to run `sudo nginx -t` and `sudo nginx -s reload` without an interactive password. Register the runner at repository Settings → Actions → Runners, and keep it dedicated to this production repository.

Flow:

```text
git push origin astro
-> CI typechecks, builds and smoke-tests the site, and builds the fetcher image
-> the production self-hosted runner resets APP_DIR onto origin/astro
-> writes production .env from GitHub Secrets
-> builds a new Docker image locally
-> starts the new Astro container on 127.0.0.1:5003 or 127.0.0.1:5004
-> checks /healthz, then warms it with a real page request
-> switches the Astro nginx upstream and reloads Nginx
-> removes the old Astro container
-> prints /healthz so the job log records which build went live
```

The fetcher and mailserver are left alone unless `DEPLOY_FETCHER_MAIL=true`;
which vhost visitors actually reach is a manual symlink, not a deploy step.

Which app the web container runs is decided by the branch you deploy.

GitHub repository secrets:

```text
APP_DIR                    # optional, defaults to /home/deploy/apps/exchangehub
APP_NAME                   # optional, defaults to exchangehub
ASTRO_BLUE_PORT            # optional, defaults to 5003
ASTRO_GREEN_PORT           # optional, defaults to 5004
NGINX_ASTRO_UPSTREAM_CONF  # optional, defaults to
                           #   /etc/nginx/conf.d/exchangehub-astro-upstream.conf
PROD_ENV                   # full production .env content, shared by both stacks
```

GitHub repository **variables** (Settings → Secrets and variables → Actions →
Variables):

```text
SWITCH_NGINX        # 'true' (default); 'false' stages without moving traffic
DEPLOY_FETCHER_MAIL # 'false' (default); 'true' makes this branch deploy the
                    # mailserver and fetcher too — set it once main is retired
```

The mailserver and the fetcher are one container each, shared by both stacks:
whichever deploy ran last owns them. While `main` still exists it deploys them,
so this branch leaves them alone — recreating them would restart the fetcher
and interrupt mail for a change that only touches the web tier. Once `main` is
retired, nothing else deploys them: set `DEPLOY_FETCHER_MAIL=true` then, or the
fetcher runs forever on whatever image main last built.

### Which app is serving

The **branch** is the switch, and each branch carries its own deploy workflow:

- push or dispatch **`astro`** → this branch's workflow → the Astro app
- push or dispatch **`main`** → main's untouched workflow → the Flask app

Both reset the same `APP_DIR` checkout and write the same nginx upstream, so
whichever ran last is what production serves. They share one concurrency group,
so the two can never interleave.

### First cutover

`/healthz` deliberately reads no rate data, so it cannot tell a working deploy
from one that cannot reach R2 — and on this site R2 is the only source of
rates, with a failed read falling back to local files that are empty. That
renders as a site with no rates rather than an error, which no health check
catches. So do the first switch in two runs:

1. Set `SWITCH_NGINX=false`, run Deploy. The Astro container is built,
   health-checked and warmed on the idle port; nginx is not touched and
   visitors stay on the old app. The job log prints the port and the curls to
   run against it.
2. Check a real page has real rates. Then set `SWITCH_NGINX=true` (or delete
   the variable) and run Deploy again to move traffic.

### Switching between the two

The two stacks run side by side on separate ports, so switching is an nginx
vhost swap — seconds, no rebuild, and the other stack stays up the whole time.

| | Flask (v1) | Astro (v2) |
| :--- | :--- | :--- |
| Ports | 5001 / 5002 | 5003 / 5004 |
| Upstream | `exchangehub_backend` | `exchangehub_astro_backend` |
| Upstream file | `conf.d/exchangehub-upstream.conf` | `conf.d/exchangehub-astro-upstream.conf` |
| vhost | `deploy/nginx-exchangehub.conf` | `deploy/nginx-exchangehub-astro.conf` |

**Only one vhost may be enabled.** They share a `server_name`, and with both
enabled nginx does not fail — it warns about a conflicting server name and
silently serves whichever it loaded first.

```bash
# to Astro
sudo rm -f /etc/nginx/sites-enabled/exchangehub.conf
sudo ln -sf /etc/nginx/sites-available/exchangehub-astro.conf \
            /etc/nginx/sites-enabled/exchangehub-astro.conf
sudo nginx -t && sudo nginx -s reload

# back to Flask
sudo rm -f /etc/nginx/sites-enabled/exchangehub-astro.conf
sudo ln -sf /etc/nginx/sites-available/exchangehub.conf \
            /etc/nginx/sites-enabled/exchangehub.conf
sudo nginx -t && sudo nginx -s reload
```

Deploying never moves traffic by itself: pushing `astro` builds and
health-checks the site on 5003/5004 and stops there. The vhost decides who
sees it.

`/healthz` says which one actually answered. The version is baked into each
image, so it reports the container's own identity rather than a config value:

```console
$ curl -s https://ratehubfx.com/healthz
{"ok":true,"service":"exchangehub","version":2,"stack":"astro","build":"b11ec1a","color":"green"}
```

| Field     | Meaning                                                    |
| :-------- | :--------------------------------------------------------- |
| `version` | `1` = the Flask app, `2` = the Astro app                    |
| `stack`   | the same answer in words                                    |
| `build`   | git short SHA the image was built from                      |
| `color`   | which half of the blue/green pair this container is         |

`ok` and `service` are unchanged, so anything already polling them still works.

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
SITE_URL=https://ratehubfx.com
CONTACT_SECRET=GENERATE_A_LONG_RANDOM_SECRET
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
sudo -u deploy git clone git@github.com:YOUR_ORG/YOUR_REPO.git /home/deploy/apps/exchangehub
cd /home/deploy/apps/exchangehub
sudo cp deploy/nginx-ratehubfx-astro-proxy.conf /etc/nginx/snippets/ratehubfx-astro-proxy.conf
sudo cp deploy/nginx-exchangehub-astro.conf /etc/nginx/sites-available/exchangehub-astro.conf
sudo ln -s /etc/nginx/sites-available/exchangehub-astro.conf /etc/nginx/sites-enabled/exchangehub-astro.conf
echo 'upstream exchangehub_astro_backend { server 127.0.0.1:5003; }' | sudo tee /etc/nginx/conf.d/exchangehub-astro-upstream.conf
sudo nginx -t
sudo systemctl reload nginx
```

The snippet must be in place before the vhost is enabled, or `nginx -t` fails
on the missing include. Edit the vhost and replace the domain with your own. If
the deploy user cannot reload Nginx without a password, allow only these
commands with sudo:

```text
deploy ALL=(root) NOPASSWD: /usr/sbin/nginx -t, /usr/sbin/nginx -s reload
```

Production traffic goes through Nginx to one active web container. The fetcher container is restarted as a single instance, so local and production do not both write R2.

SEO pair pages

- Every pair page comes from one model built in `src/lib/pair.ts`: latest rate,
  converter table, chart series, statistics, explanatory copy and FAQ. The head
  tags and JSON-LD are assembled in `src/layouts/Layout.astro`.
- Each page emits a canonical URL, a meta description carrying the live rate,
  Open Graph and Twitter card tags, and a JSON-LD graph of Organization,
  WebSite, WebPage and BreadcrumbList — plus FAQPage and
  ExchangeRateSpecification on pair pages.
- `sitemap.xml` reports two kinds of `lastmod`: data pages take the newest
  stored rate timestamp, the info pages take `INFO_CONTENT_LAST_MODIFIED` from
  `src/lib/info.ts`. Bump that constant when the copy changes.
- Because the site translates in the browser rather than serving one URL per
  language, there is deliberately no `hreflang` and no `og:locale:alternate` —
  they would point at pages that do not exist.

Permissions and cron

- With `LOCAL_STORAGE_ENABLED=false`, the cron user does not need write access to `wp-content/uploads`.
- If local writes are enabled, ensure the user running the cron job can write to the uploads directory. Example cron to run every 5 minutes:

```cron
*/5 * * * * cd /path/to/repo && WP_UPLOADS=/var/www/html/wp-content/uploads /path/to/venv/bin/python3 fetch_rates.py >> /path/to/repo/fetch.log 2>&1
```

- Alternatively set `WP_UPLOADS` to a path inside the repo for testing (e.g., `wp-content/uploads`).

Atomic writes & caching

- `fetch_rates.py` writes to temporary files and `os.replace()` to avoid half-written files.
- The fetcher still writes a `rates.html` partial beside the JSON. Nothing reads
  it any more — it existed for the WordPress theme include, which went with the
  Flask app. Harmless, but do not build anything new on it.

Analytics

**There is none.** The Flask app carried a GA4 tag and about fifteen custom
events, including Web Vitals, `js_error` and `contact_submit_success`. None of
that was carried over to the Astro site, so real-user performance and
conversion data stopped at the cutover. Cloudflare Analytics still covers
traffic, bandwidth, cache hit ratio and security events without any tag, and
the nginx access log feeds `deploy/goaccess-report.sh`. Re-adding a tag is a
decision, not an oversight to fix silently: it changes what the privacy policy
has to disclose and what a consent banner has to gate.

Cloudflare

The zone is proxied through Cloudflare, which terminates TLS for visitors,
caches the HTML at the edge and re-connects to the origin over TLS.

**`deploy/CLOUDFLARE.md` is the runbook** -- what each layer does, the order to
turn them on in, the command that proves each one is working and what every
outcome means, plus a table of the failure modes and what causes them.

Two scripts do the work:

```bash
sudo bash deploy/cloudflare-realip.sh                       # teach nginx the edge ranges
python3 scripts/cloudflare_setup.py                         # report, changes nothing
python3 scripts/cloudflare_setup.py --cache-rule --apply    # cache HTML at the edge
```

The nginx side lives in `deploy/nginx-exchangehub-astro.conf` and is **not**
deployed by pushing -- `deploy_astro.sh` only rewrites the blue/green upstream.
Copy it to `/etc/nginx/sites-available/` and symlink it, as in the bootstrap
above.

Monitoring and hardening

Already collected, and mostly unused:

- **Cloudflare Analytics** covers traffic, bandwidth, cache hit ratio and
  Security Events for free, with no tag on the page. It is the only analytics
  this site has — see "Analytics" above.

Added by `deploy/nginx-exchangehub-astro.conf`:

- `log_format ratehubfx_astro` keeps nginx's `combined` prefix and appends `host=`,
  `rt=` (what the visitor waited) and `urt=` (what the app took). The gap
  between the two is nginx plus network.
- Security headers on every response, errors included: HSTS,
  `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Permissions-Policy`. **No CSP** -- the app inlines its scripts and styles and
  loads jsdelivr, Google Fonts and Google Translate, so a policy that is both
  useful and non-breaking has to be worked out rather than guessed at.
- Rate limits on `/contact` (10 r/m, it sends mail) and `/api/` (300 r/m with a
  burst, since one page load fires five or six calls). Both return 429.

Rate limits key on the client address, so **run `deploy/cloudflare-realip.sh`
first** -- until nginx knows Cloudflare's ranges every visitor shares a handful
of edge addresses and they throttle each other.

Turn the log into a dashboard:

```bash
sudo apt-get install -y goaccess
sudo bash deploy/goaccess-report.sh            # one-off HTML report
sudo bash deploy/goaccess-report.sh --live     # keeps updating
```

The report lists visitor addresses and every URL requested. Keep it behind a
password or read it locally over `scp`; do not serve it from a public vhost.


Ad network review

Before applying to an ad network, the site has to look like a publisher rather
than a page generator. What is already in place: About, Contact, Privacy
Policy, Terms and Disclaimer, linked from the footer of every page and each
carrying a "Last updated" date; the privacy copy names Google as a third-party
vendor, explains the cookies the site sets itself, and links the opt-outs; the
disclaimer states plainly that the rates are reference data and not advice.

Two things still need a decision.

**A consent management platform.** Google's EU user consent policy requires a
certified CMP before serving ads to visitors in the EEA, the UK or
Switzerland. The site sets a language cookie, the translation widget's cookie
and the contact form's anti-automation cookie, none of which are currently
gated behind consent. Google's own CMP is configured in the AdSense interface
and needs no code here; a third-party CMP would.

**The long-tail pair pages.** `NOINDEX_LONGTAIL_PAIRS=true` marks every pair
outside the header menu `noindex` and drops it from `sitemap.xml`, leaving the
38 curated pairs — see `pairIsNoindex` in `src/lib/config.ts`. The pages it
hides are one template with the currency names swapped, which is what a
reviewer reads as scaled content. They stay reachable and keep working for
visitors; they simply stop being submitted for indexing. Turn the variable off
again once those pairs carry writing of their own.

`ads.txt` is deliberately absent. A file listing no authorised sellers is
worse than no file at all — buyers read it as "nobody may sell this
inventory". Create `public/ads.txt` with the real line once the publisher ID
exists:

```text
google.com, pub-XXXXXXXXXXXXXXXX, DIRECT, f08c47fec0942fa0
```
