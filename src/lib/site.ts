import "./env";

// Every absolute URL the site emits — canonical, og:url, the JSON-LD @ids,
// sitemap.xml, the Sitemap: line in robots.txt — has to be the address a
// visitor actually typed. `Astro.url.origin` is not: nginx terminates TLS and
// proxies to the Node server over plain HTTP, so the request the app sees is
// `http://` on an internal port, and every canonical came out as
// `http://ratehubfx.com/…` — a different URL from the https one Google
// crawls. The Flask app this replaces solved it with ProxyFix; this is the
// same job, reading the headers nginx sets (see deploy/nginx-ratehubfx-proxy.conf).
//
// SITE_URL wins when set, so the answer cannot depend on a header at all.
// Otherwise X-Forwarded-Proto and X-Forwarded-Host are trusted — which is
// only safe because nginx overwrites both on every proxied request, and the
// Node server is bound to localhost where nothing else can reach it.
const CONFIGURED = (process.env.SITE_URL ?? process.env.PUBLIC_SITE_URL ?? "").trim().replace(/\/+$/, "");

/** The brand as the page copy writes it — header, footer, every info page. */
export const SITE_NAME = "ExchangeHub";
/** The domain reads as a second brand, so it is declared as the same one. */
export const SITE_ALTERNATE_NAME = "RateHubFX";

export function siteOrigin(request: Request, url: URL): string {
  if (CONFIGURED) return CONFIGURED;
  const forwardedProto = request.headers.get("x-forwarded-proto")?.split(",")[0].trim();
  const forwardedHost = request.headers.get("x-forwarded-host")?.split(",")[0].trim();
  const proto = forwardedProto || url.protocol.replace(/:$/, "");
  const host = forwardedHost || request.headers.get("host")?.trim() || url.host;
  return `${proto}://${host}`;
}

/** True when the visitor reached the site over HTTPS, TLS termination included
 *  — so a cookie can be marked Secure without the origin ever seeing https. */
export function isSecureRequest(request: Request, url: URL): boolean {
  return siteOrigin(request, url).startsWith("https://");
}
