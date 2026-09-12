import type { APIRoute } from "astro";
import { MENU_GROUPS, RATE_PAIRS, pairUrl } from "../lib/config";
import { INFO_LINKS } from "../lib/info";
import { siteOrigin } from "../lib/site";

export const prerender = false;

function escapeXml(value: string): string {
  return value.replace(/[<>&'"]/g, (char) =>
    ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", '"': "&quot;" }[char] as string));
}

// Same set the Flask sitemap listed: the home page, the chart tool, the policy
// pages, every configured pair, and the hand-picked menu pairs (which include
// derived pairs that have no stored file of their own).
export const GET: APIRoute = ({ request, url }) => {
  const origin = siteOrigin(request, url);
  const paths = [
    "/",
    "/chart",
    ...INFO_LINKS.map((link) => link.href),
    ...RATE_PAIRS.map(([base, target]) => pairUrl(base, target)),
    ...Object.entries(MENU_GROUPS).flatMap(([base, targets]) =>
      targets.filter((target) => target !== base).map((target) => pairUrl(base, target))),
  ];
  const seen = [...new Set(paths)];
  const lastmod = new Date().toISOString().slice(0, 10);
  const body = `<?xml version="1.0" encoding="UTF-8"?>\n`
    + `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n`
    + seen.map((path) => `  <url><loc>${escapeXml(origin + path)}</loc><lastmod>${lastmod}</lastmod></url>`).join("\n")
    + `\n</urlset>\n`;
  return new Response(body, { headers: { "content-type": "application/xml; charset=utf-8" } });
};
