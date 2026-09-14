import type { APIRoute } from "astro";
import { siteOrigin } from "../lib/site";
import { XML_HEADERS, renderUrlset, sectionEntries } from "../lib/sitemap";

export const prerender = false;

// `/sitemap-pages.xml`, `/sitemap-currencies.xml`, `/sitemap-pairs-vnd.xml`.
// An unknown section 404s rather than answering with an empty urlset, so a
// stale link in Search Console reads as gone instead of as a section that has
// quietly lost all its pages.
export const GET: APIRoute = async ({ params, request, url }) => {
  const entries = await sectionEntries((params.section ?? "").toLowerCase());
  if (!entries) {
    return new Response("Not found", { status: 404, headers: { "content-type": "text/plain; charset=utf-8" } });
  }
  return new Response(renderUrlset(siteOrigin(request, url), entries), { headers: XML_HEADERS });
};
