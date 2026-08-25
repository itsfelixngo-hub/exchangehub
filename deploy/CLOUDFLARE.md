# Cloudflare setup for ratehubfx.com

Everything Cloudflare does for this site, what each piece is for, how to turn
it on, and — for each one — the command that proves it is working and what the
output means.

Read it top to bottom the first time: the layers depend on each other, and
turning one on out of order takes the site down in ways that are easy to
misread.

---

## The shape of it

```
visitor ──TLS──> Cloudflare edge ──TLS──> nginx (VPS) ──HTTP──> gunicorn
                  cache, WAF          SNI splits two sites      blue/green
                                      ratehubfx / alogweb       5001 or 5002
```

Two sites share one VPS and one pair of ports. They are told apart by SNI, so
each needs its own certificate. `alogweb` was configured first; its file sorts
before `exchangehub.conf`, which makes it the implicit default server — any
request whose SNI matches neither lands there.

| Thing | Where it lives |
|---|---|
| Site config | `/etc/nginx/sites-enabled/exchangehub.conf` — copied by hand from `deploy/nginx-exchangehub.conf` |
| Shared proxy block | `/etc/nginx/snippets/ratehubfx-proxy.conf` |
| Upstream (blue/green port) | `/etc/nginx/conf.d/exchangehub-upstream.conf` — **rewritten by every deploy** |
| Cloudflare address ranges | `/etc/nginx/conf.d/00-cloudflare-realip.conf` |
| Certificates | `/etc/ssl/cloudflare/` |

Only the upstream file is automatic. Pushing to `main` never updates the site
config; `deploy_blue_green.sh` writes the upstream and reloads nginx, nothing
more.

---

## 1. DNS through Cloudflare

`ratehubfx.com` and `www` are proxied (orange cloud). `mail.ratehubfx.com` is
deliberately **not** — mail cannot go through the HTTP proxy.

**Verify.** The public address should be Cloudflare's, not the origin:

```bash
dig +short ratehubfx.com
curl -s -D - -o /dev/null https://ratehubfx.com/ | grep -i '^cf-ray'
```

A `cf-ray` header means the request went through Cloudflare. Its suffix is the
data centre that served you (`...-SIN` is Singapore).

To talk to the origin directly, bypassing Cloudflare entirely, pin the address:

```bash
curl -sk --resolve ratehubfx.com:443:139.180.142.141 https://ratehubfx.com/
```

That is the single most useful debugging tool here: it tells you whether a
problem is in nginx or at the edge.

---

## 2. TLS to the origin

Visitors terminate TLS at the edge; Cloudflare then opens its own connection to
the origin. The certificate the origin presents therefore only has to be
trusted by Cloudflare, which is what a **Cloudflare Origin Certificate** is
for: free, valid 15 years, no renewal job.

Cloudflare's SSL/TLS mode decides what that second hop looks like:

| Mode | CF → origin | Verdict |
|---|---|---|
| Flexible | plain HTTP :80 | visitor sees a padlock, the second hop is in the clear |
| Full | HTTPS, certificate **not** checked | any certificate passes, including the wrong site's |
| Full (strict) | HTTPS, certificate checked | what this zone uses |

### Setting it up

1. Dashboard → zone → SSL/TLS → Origin Server → **Create Certificate**. Do this
   per zone: the `alogweb` certificate in `/etc/ssl/cloudflare/` covers only
   `alogweb.com` and `*.alogweb.com` and cannot be reused here.
2. Install:

```bash
sudo install -d -m 0755 /etc/ssl/cloudflare
sudo nano /etc/ssl/cloudflare/ratehubfx.com.pem   # the certificate
sudo nano /etc/ssl/cloudflare/ratehubfx.com.key   # the private key
sudo chmod 644 /etc/ssl/cloudflare/ratehubfx.com.pem
sudo chmod 600 /etc/ssl/cloudflare/ratehubfx.com.key
```

3. Install the site config, then `sudo nginx -t && sudo nginx -s reload`.
4. **Only then** set the mode to Full (strict).

That order matters. Before the `:443` block exists, SNI `ratehubfx.com` falls
through to the alogweb vhost — so switching to Full first serves alogweb's
content under this domain, and Full (strict) fails 526.

### Verify

Which certificate does each name get?

```bash
for d in ratehubfx.com www.ratehubfx.com alogweb.com; do
  printf '%-20s ' "$d"
  echo | openssl s_client -connect 139.180.142.141:443 -servername "$d" 2>/dev/null \
    | openssl x509 -noout -ext subjectAltName | tail -1
done
```

Expect each name to get its own SANs:

```
ratehubfx.com        DNS:*.ratehubfx.com, DNS:ratehubfx.com
www.ratehubfx.com    DNS:*.ratehubfx.com, DNS:ratehubfx.com
alogweb.com          DNS:*.alogweb.com, DNS:alogweb.com
```

Is the mode actually Full? There is no header that says so, but the app gives
it away. It builds absolute URLs from `X-Forwarded-Proto`, which nginx sets
from the scheme Cloudflare connected with:

```bash
curl -s --compressed https://ratehubfx.com/ | grep -o '<link rel="canonical" href="[^"]*"'
```

`https://ratehubfx.com/` means the CF→origin hop is TLS. `http://` means the
zone is still on Flexible, whatever the padlock suggests.

---

## 3. Real visitor addresses

Behind a proxy, `$remote_addr` is a Cloudflare edge address. Logs, `X-Real-IP`
and anything keyed on the client — the nginx rate limits, the contact form's
own limiter — all see Cloudflare instead of the visitor.

```bash
sudo bash deploy/cloudflare-realip.sh
sudo nginx -t && sudo nginx -s reload
```

The script fetches Cloudflare's published ranges, writes them as
`set_real_ip_from` plus `real_ip_header CF-Connecting-IP`, and refuses to
install a truncated list if the fetch half-fails. Re-run it occasionally;
Cloudflare does add ranges.

**Run this before relying on the rate limits.** Without it every visitor shares
a handful of addresses and they throttle each other.

### Verify

```bash
grep -c set_real_ip_from /etc/nginx/conf.d/00-cloudflare-realip.conf   # ~22
sudo tail -3 /var/log/nginx/ratehubfx.access.log
```

The first field should be a real visitor address, not a Cloudflare one. A
forged header from an address outside those ranges is ignored, which is the
point — spoofing `CF-Connecting-IP` only works from Cloudflare.

---

## 4. Caching HTML at the edge

Cloudflare does **not** cache HTML by default. It caches static file
extensions and passes everything else through, so the `Cache-Control` the app
sends is ignored at the edge and every request reaches the origin.

```bash
python3 scripts/cloudflare_setup.py                        # report, changes nothing
python3 scripts/cloudflare_setup.py --cache-rule --apply
```

The rule marks the zone cacheable with `edge_ttl: respect_origin` — the TTL
stays defined in one place, the app's `PAGE_CACHE_SECONDS` — and excludes
`/contact`, which carries a per-visitor token and is served `no-store`.

`--apply` re-reads the ruleset afterwards and prints it, so you can see the
rule landed rather than inferring it from cache headers.

This is only safe because the server renders one page for every visitor.
Timestamps travel as UTC in `<time datetime="...Z">` and the browser converts
them; a per-visitor render would make the pages uncacheable.

### Verify

```bash
for i in 1 2 3; do
  curl -s -D - -o /dev/null --compressed https://ratehubfx.com/ | grep -i cf-cache-status
done
curl -s -D - -o /dev/null --compressed https://ratehubfx.com/contact/ | grep -i cf-cache-status
```

| Output | Meaning |
|---|---|
| `MISS` then `HIT` | working — the edge is serving it |
| `DYNAMIC` on `/` | Cloudflare declined to cache: no rule, or it does not match |
| `DYNAMIC` on `/contact/` | correct, that path is excluded on purpose |
| `EXPIRED` | was cached, TTL passed, revalidating |
| `BYPASS` | something told the edge to skip the cache |

`MISS` on a page you have not visited before is normal — the cache is per URL
and per data centre.

Use a **GET**, not `curl -I`. And note that each cache entry is per data
centre, so a colleague elsewhere may see `MISS` while you see `HIT`.

---

## 5. Authenticated Origin Pulls (optional)

The origin answers on its public address, so anyone can reach it directly,
bypass the CDN, and forge `X-Forwarded-For` — which the contact form's rate
limit is keyed on. Authenticated Origin Pulls makes nginx demand a client
certificate that only Cloudflare has.

Off by default here, matching the alogweb vhost. Three steps, **in this order**:

```bash
# 1. Cloudflare side
python3 scripts/cloudflare_setup.py --origin-pulls --apply

# 2. the CA nginx will check against
sudo curl -fsSLo /etc/ssl/cloudflare/origin-pull-ca.pem \
  https://developers.cloudflare.com/ssl/static/authenticated_origin_pull_ca.pem

# 3. uncomment ssl_client_certificate and ssl_verify_client, then
sudo nginx -t && sudo nginx -s reload
```

Uncommenting before step 1 answers **every request with 400**.

### Verify

```bash
curl -s -o /dev/null -w '%{http_code}\n' --compressed https://ratehubfx.com/   # 200, via CF
curl -sk -o /dev/null -w '%{http_code}\n' \
  --resolve ratehubfx.com:443:139.180.142.141 https://ratehubfx.com/           # 400
```

Through Cloudflare: 200. Straight to the origin: 400, because you have no
Cloudflare client certificate. That 400 is the feature working.

---

## API token

One token, scoped to this zone:

| Permission | Needed for |
|---|---|
| Zone – Zone – Read | looking the zone up by name |
| Zone – DNS – Edit | `scripts/import_cloudflare_mail_dns.py` |
| Zone – Cache Rules – Edit | `--cache-rule` |
| Zone – SSL and Certificates – Edit | `--origin-pulls`, issuing origin certs by API |

Keep **IP Address Filtering** on. It restricts the token to addresses you
name, which is why the script has to run from the VPS rather than a laptop.

Do not pass the token on the command line — it lands in shell history and in
any screenshot. With `CF_API_TOKEN` unset the script prompts for it without
echoing:

```bash
CF_ZONE_NAME=ratehubfx.com python3 scripts/cloudflare_setup.py --cache-rule --apply
```

Origin CA Keys (`X-Auth-User-Service-Key`) still work but Cloudflare removes
them on **2026-09-30**; use a token.

---

## Full check, top to bottom

```bash
# through Cloudflare
curl -s -D - -o /dev/null --compressed https://ratehubfx.com/ \
  | grep -iE 'cf-cache-status|cf-ray|cache-control|strict-transport|x-frame'

# the origin directly
curl -sk -D - -o /dev/null --resolve ratehubfx.com:443:139.180.142.141 \
  https://ratehubfx.com/ | grep -iE 'HTTP/|content-encoding'

# both sites still separate
curl -s --compressed https://ratehubfx.com/ | grep -o '<title>[^<]*'
curl -s --compressed https://alogweb.com/   | grep -o '<title>[^<]*'

# port 80 redirects
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' http://ratehubfx.com/

# the origin is healthy underneath it all
curl -s https://ratehubfx.com/healthz
```

---

## When something looks wrong

| Symptom | Cause | Fix |
|---|---|---|
| `grep '<title>'` prints nothing, status is 200 | response is gzipped and curl was not asked to decode | add `--compressed`. If the origin gzips for a client that never asked, that is a config bug — nothing should set `proxy_set_header Accept-Encoding` |
| ratehubfx serves alogweb's content | no `:443` block for this zone, SNI falls through to the default server | install the site config before changing the SSL mode |
| **526** from Cloudflare | Full (strict) but the origin certificate does not cover this name | check the SANs (§2); issue a certificate for this zone |
| `[emerg] duplicate upstream` | the site config `include`s `conf.d/exchangehub-upstream.conf`, which Ubuntu's `nginx.conf` already globs | leave that include commented |
| `[emerg] a duplicate default server` | two vhosts claim `default_server` on one port | only one may |
| `[emerg] ... shared memory zone "SSL" conflicts` | two vhosts reuse an `ssl_session_cache` name at different sizes | give each its own zone name |
| `[emerg] unknown directive "http2"` | `http2 on;` needs nginx ≥ 1.25.1 | use `listen 443 ssl http2;` |
| `cf-cache-status: DYNAMIC` on `/` | no cache rule, or it does not match | `scripts/cloudflare_setup.py` to see whether a rule exists |
| API `9109` — cannot use token from location | token restricted by IP, this machine is not listed | run it from an allowed address |
| API `10000` — authentication error | token lacks the scope for that call | add the permission above; the script lists every missing scope in one run |
| Rate limits fire for ordinary visitors | `cloudflare-realip.sh` has not run, so everyone shares a few edge addresses | run it, reload nginx |
| 502 after a deploy | the site config points at a fixed port instead of the upstream | `proxy_pass http://exchangehub_backend` — the port alternates 5001/5002 |

---

## Operational notes

- **Rates lag up to `PAGE_CACHE_SECONDS` at the edge** (300 s in production),
  which matches how often the fetcher runs. To change it, change that variable
  — the rule follows the origin, so there is nothing to edit at Cloudflare.
- **Purging.** After a change that must appear at once, purge from the
  dashboard (Caching → Configuration → Purge Everything) or wait out the TTL.
- **The site config is not deployed.** After `git pull`, copy it and reload, or
  the change stays in the repo.
- **Brotli is left off at the origin** on purpose: Cloudflare compresses to the
  visitor itself, so origin brotli would only affect the CF→origin hop.
- **`mail.ratehubfx.com` is outside all of this** — unproxied, not served by
  nginx, unaffected by SSL-mode changes.
