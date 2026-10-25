import type { APIRoute } from "astro";
import { siteOrigin } from "../lib/site";
import { XML_HEADERS, dataLastmod, renderUrlset, sitemapEntries } from "../lib/sitemap";

export const prerender = false;

// The whole sitemap: home, the info pages and the 15 canonical core pairs.
// robots.txt points here. See src/lib/sitemap.ts.
export const GET: APIRoute = async ({ request, url }) => {
  const origin = siteOrigin(request, url);
  return new Response(renderUrlset(origin, sitemapEntries(await dataLastmod())), { headers: XML_HEADERS });
};
