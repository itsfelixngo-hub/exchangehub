# astro-web

The ExchangeHub site: the pages nginx serves at ratehubfx.com. It replaces the
Flask app in the repo root, which is now only the rate fetcher.

Server-rendered on demand (`output: 'server'`, `@astrojs/node` standalone) —
not static — because every HTML page is a per-visitor render: the header
language follows the `site_lang` cookie, and the rate board, converter and
hero follow the country that cookie or `CF-IPCountry` resolves to.

## Where the data comes from

The fetcher writes one JSON file per currency pair. This app reads them, from
Cloudflare R2 when `R2_ENABLED=true` and from `$WP_UPLOADS/rates/` otherwise —
and falls back to the local files when an R2 read fails, so a credentials
problem degrades instead of blanking the site.

Only a couple of dozen pairs are stored. Everything else is triangulated
through a USD table built from them (`deriveRateFromUsdTable` in
`src/lib/rates.ts`), which is why `/krw-thb` has a page without a `krw_thb.json`
ever existing.

## Configuration

There is no `.env` of its own to maintain: `src/lib/env.ts` walks up from the
working directory to the repo root and loads the `.env` there, the same file
the fetcher uses. A local `astro-web/.env` can override individual keys for
development — the nearest file wins.

Most keys are the ones the fetcher already documents in the repo root
`.env.sample` — the R2 credentials and the `CONTACT_*` block. The ones this app
adds:

| Key                     | Default          | What it does                                    |
| :---------------------- | :--------------- | :---------------------------------------------- |
| `SITE_URL`              | inferred         | Public origin for every absolute URL it emits    |
| `WP_UPLOADS`            | `../wp-content/uploads` | Where the fetcher's rate JSON lives      |
| `PAIR_CONCURRENCY`      | `6`              | Pair histories loaded at once (`mapLimited`)     |
| `PAIR_CHART_MAX_POINTS` | `600`            | Points in the pair-page chart before downsampling |
| `CONTACT_SECRET`        | random per boot  | Signs the contact form's rotation challenge       |

`SITE_URL` is the one worth setting deliberately: every absolute URL the site
emits (canonical, `og:url`, the JSON-LD `@id`s, `sitemap.xml`, `robots.txt`)
comes from it. Without it the app infers the origin from `X-Forwarded-Proto` /
`Host`, which is correct behind the nginx config in `deploy/` but silently
emits `http://` canonicals if those headers ever go missing.

`APP_VERSION`, `APP_BUILD` and `APP_COLOR` are reported by `/healthz` but are
image arguments, not `.env` keys — see the `ARG`s in `Dockerfile`.

## Commands

Run from `astro-web/`. Node 22.12+ (Astro 7 refuses to start on 20).

| Command          | Action                                                       |
| :--------------- | :----------------------------------------------------------- |
| `npm ci`         | Install exactly what package-lock.json pins                   |
| `npm run dev`    | Dev server on `$PORT` (4321)                                  |
| `npm run check`  | Typecheck `.astro` and `.ts` — CI gates on this               |
| `npm run build`  | Build to `dist/`                                              |
| `npm start`      | Run the built server                                          |
| `npm run smoke`  | Boot `dist/` against fixture rates and assert on the routes    |

`npm run smoke` needs a build first. It writes its own fixture rate files to a
temp directory and turns R2 off, so it needs no credentials and asserts on
known numbers.

## Caching

Two layers, both on `R2_READ_CACHE_SECONDS` (default 60s):

- the rate files themselves, and the USD table derived from them
- the expensive page models built on top — the movers list and the rate board,
  each about forty pair histories (`memoByTtl` in `src/lib/rates.ts`)

A cold render costs roughly 250ms and a warm one under 10ms, so
`scripts/deploy_astro.sh` fires one real request at a new container before
nginx points at it. One request is enough: unlike gunicorn's several worker
processes, this is one process with one cache.

HTML is sent `Cache-Control: private` because the pages are per-visitor; the
JSON under `/api/` is not, and is cacheable at the edge. See
`deploy/CLOUDFLARE.md` before adding a cache rule that touches HTML.

Files in `public/` are served by the Node adapter's static handler, which
stamps `max-age=0` on everything outside `/_astro/` — so a home page with two
dozen flag icons on it revalidates two dozen files per visit. That handler runs
before the app's own middleware, so the fix lives in the nginx vhost
(`deploy/nginx-exchangehub.conf`), not in this codebase.

## Deployment

`scripts/deploy_astro.sh` from the repo root, which the Deploy workflow calls
on the self-hosted runner when the `WEB_STACK` repository variable is `astro`
(its default). It builds `Dockerfile` here, health-checks and warms the new
container on the idle blue/green port, switches the nginx upstream onto it, and
only then removes the old one and any Flask web container it supersedes.

Setting `WEB_STACK=flask` rolls back the same way. See "Which app is serving"
in the repo root README.

`/healthz` reports `version: 2` and `stack: "astro"` so a single curl says
which stack answered; `1`/`"flask"` is the app this one replaces.
