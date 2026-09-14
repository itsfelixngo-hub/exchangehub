import { defineMiddleware } from "astro:middleware";
import { siteOrigin } from "./lib/site";

// Astro's own origin check is turned off in astro.config.mjs and replaced by
// this one, because it compared the browser's Origin against the scheme of the
// internal nginx -> Node hop and so rejected every real submission. Same rule,
// against the origin the visitor actually used.
//
// A request with no Origin header at all is allowed through: form posts from
// a browser always carry one, and the contact form's own signed rotation
// challenge is what actually gates a submission (src/lib/contact.ts).
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function isCrossOrigin(request: Request, url: URL): boolean {
  if (!UNSAFE_METHODS.has(request.method)) return false;
  const origin = request.headers.get("origin");
  if (!origin) return false;
  return origin !== siteOrigin(request, url);
}

// Every HTML page here is a per-visitor render: the header's language follows
// the `site_lang` cookie, and the home board, converter and hero follow the
// country that cookie (or the CF-IPCountry header) resolves to. Without a
// header saying so, any shared cache in front of the origin — the Cloudflare
// cache rule in deploy/CLOUDFLARE.md caches HTML zone-wide — stores the first
// visitor's language and serves it to everyone else.
//
// `private` is what keeps the edge out; Cloudflare honours Vary only for
// Accept-Encoding, so listing the inputs is documentation for other caches
// rather than something CF can act on. JSON API responses depend on their
// query string alone and are left untouched.
// One canonical URL per page, the way the Flask app did it with its 301s:
// lower case, a single "-" between the codes, no trailing slash, and no
// /exchange/ prefix. Without these the same pair answers on four URLs, which
// is what search engines see as duplicated pages.
const PAIR_SEGMENT = /^([A-Za-z]{3})[-_]([A-Za-z]{3})$/;

// The JSON routes answer on their query string alone — no cookie, no country —
// so unlike the HTML above them they are safe for a shared cache to hold. The
// window matches R2_READ_CACHE_SECONDS: past it the data behind them changes
// anyway. `stale-while-revalidate` lets the edge keep serving during a refresh
// instead of queueing visitors behind one origin request.
//
// The image rule is a safety net, not the main mechanism: files in public/ are
// served by the Node adapter's own static handler, which runs before any of
// this and stamps `max-age=0` on everything outside /_astro/. Correcting that
// is nginx's job (see the location blocks in deploy/nginx-exchangehub.conf);
// this line only covers an image that is ever served by a route instead.
const STATIC_ASSET = /\.(svg|png|ico|jpg|jpeg|webp|avif|woff2?)$/i;

function staticCachePolicy(pathname: string): string | null {
  if (pathname.startsWith("/api/")) return "public, max-age=60, stale-while-revalidate=300";
  // The index and every section under it (/sitemap-pairs-vnd.xml and friends).
  if (/^\/sitemap(-[a-z-]+)?\.xml$/.test(pathname) || pathname === "/robots.txt") return "public, max-age=3600";
  if (STATIC_ASSET.test(pathname)) return "public, max-age=31536000, immutable";
  return null;
}

function canonicalPath(pathname: string): string | null {
  let path = pathname;
  if (path.length > 1 && path.endsWith("/")) path = path.replace(/\/+$/, "");
  // Case-insensitive: the pair segment below is normalised anyway, so an
  // uppercase /EXCHANGE/EUR-USD should reach the same canonical URL as the
  // lowercase one rather than 404.
  const legacy = path.match(/^\/exchange\/(.+)$/i);
  if (legacy) path = `/${legacy[1]}`;
  const pair = path.slice(1).match(PAIR_SEGMENT);
  if (pair) path = `/${pair[1].toLowerCase()}-${pair[2].toLowerCase()}`;
  return path === pathname ? null : path;
}

export const onRequest = defineMiddleware(async (context, next) => {
  if (isCrossOrigin(context.request, context.url)) {
    return new Response(`Cross-site ${context.request.method} form submissions are forbidden`, { status: 403 });
  }

  // Only GET/HEAD: redirecting a POST would drop the body (the contact form
  // posts to /contact).
  if (context.request.method === "GET" || context.request.method === "HEAD") {
    const target = canonicalPath(context.url.pathname);
    if (target) {
      return context.redirect(target + context.url.search, 301);
    }
  }

  const response = await next();

  // Successful responses only: an /api/ route that 400s on a bad pair or 500s
  // on a bad read must not have that answer held at the edge for a minute.
  if (response.ok && !response.headers.has("cache-control")) {
    const assetPolicy = staticCachePolicy(context.url.pathname);
    if (assetPolicy) {
      response.headers.set("cache-control", assetPolicy);
      return response;
    }
  }

  if (!(response.headers.get("content-type") ?? "").includes("text/html")) return response;

  if (!response.headers.has("cache-control")) {
    response.headers.set("cache-control", "private, no-cache, must-revalidate");
  }
  const vary = response.headers.get("vary");
  const parts = vary ? vary.split(",").map((part) => part.trim()).filter(Boolean) : [];
  for (const header of ["Cookie", "CF-IPCountry"]) {
    if (!parts.some((part) => part.toLowerCase() === header.toLowerCase())) parts.push(header);
  }
  response.headers.set("vary", parts.join(", "));
  return response;
});
