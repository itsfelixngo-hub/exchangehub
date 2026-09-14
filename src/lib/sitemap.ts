import { allPairs, configCurrencies, currencyUrl, pairIsNoindex, pairUrl } from "./config";
import { INFO_LINKS, INFO_CONTENT_LAST_MODIFIED } from "./info";
import { buildLatestUsdTable } from "./rates";

/**
 * The site's URLs are deliberately flat — `/vnd` and `/vnd-usd`, never
 * `/vnd/usd` — because a pair page is a page in its own right and burying it a
 * segment deeper only lengthens the URL. The hierarchy lives here instead:
 * `/sitemap.xml` is an index, and the sections below mirror the way the pages
 * nest, so a crawler reads the same shape the breadcrumbs describe.
 *
 *   /sitemap.xml               index
 *     /sitemap-pages.xml       home, chart tool, info pages
 *     /sitemap-currencies.xml  one hub per currency
 *     /sitemap-pairs-vnd.xml   the pairs based on VND — one file per hub
 */
export type SitemapEntry = { path: string; lastmod: string };

export function escapeXml(value: string): string {
  return value.replace(/[<>&'"]/g, (char) =>
    ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", '"': "&quot;" }[char] as string));
}

function day(timestampSeconds: number): string {
  return new Date(timestampSeconds * 1000).toISOString().slice(0, 10);
}

/**
 * Data pages carry the date of the newest stored rate; the info pages carry
 * the date their copy last changed. Stamping today onto everything — which is
 * what this used to do — tells Google the terms page is rewritten on every
 * crawl, and a site whose every URL claims to have just changed gets its
 * lastmod ignored across the board.
 *
 * The timestamp comes from the same memoised table the home page renders from,
 * so the sitemap adds no R2 traffic of its own.
 */
export async function dataLastmod(): Promise<string> {
  const { latestTs } = await buildLatestUsdTable();
  return latestTs ? day(latestTs) : new Date().toISOString().slice(0, 10);
}

/**
 * Every pair the site is willing to have indexed. A page carrying `noindex`
 * must not also be advertised here: the sitemap says "please index this", the
 * page says the opposite, and Google logs the contradiction against the whole
 * file.
 */
export function indexablePairs(): [string, string][] {
  return allPairs().filter(([base, target]) => !pairIsNoindex(base, target)) as [string, string][];
}

/** Currencies that head at least one indexable pair. */
function indexableBases(): string[] {
  const bases = new Set(indexablePairs().map(([base]) => base));
  return configCurrencies().filter((code) => bases.has(code));
}

export function sectionNames(): string[] {
  return ["pages", "currencies", ...indexableBases().map((code) => `pairs-${code.toLowerCase()}`)];
}

/** The entries of one section, or null when the name names no section. */
export async function sectionEntries(section: string): Promise<SitemapEntry[] | null> {
  const lastmod = await dataLastmod();

  if (section === "pages") {
    return [
      { path: "/", lastmod },
      { path: "/chart", lastmod },
      { path: "/analysis", lastmod },
      ...INFO_LINKS.map((link) => ({ path: link.href, lastmod: INFO_CONTENT_LAST_MODIFIED })),
    ];
  }

  if (section === "currencies") {
    return configCurrencies().map((code) => ({ path: currencyUrl(code), lastmod }));
  }

  const pairsOf = section.match(/^pairs-([a-z]{3})$/);
  if (pairsOf) {
    const base = pairsOf[1].toUpperCase();
    if (!indexableBases().includes(base)) return null;
    return indexablePairs()
      .filter(([pairBase]) => pairBase === base)
      .map(([pairBase, target]) => ({ path: pairUrl(pairBase, target), lastmod }));
  }

  return null;
}

export function renderUrlset(origin: string, entries: SitemapEntry[]): string {
  return `<?xml version="1.0" encoding="UTF-8"?>\n`
    + `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n`
    + entries.map(({ path, lastmod }) =>
        `  <url><loc>${escapeXml(origin + path)}</loc><lastmod>${lastmod}</lastmod></url>`).join("\n")
    + `\n</urlset>\n`;
}

export function renderIndex(origin: string, sections: { name: string; lastmod: string }[]): string {
  return `<?xml version="1.0" encoding="UTF-8"?>\n`
    + `<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n`
    + sections.map(({ name, lastmod }) =>
        `  <sitemap><loc>${escapeXml(`${origin}/sitemap-${name}.xml`)}</loc><lastmod>${lastmod}</lastmod></sitemap>`).join("\n")
    + `\n</sitemapindex>\n`;
}

export const XML_HEADERS = { "content-type": "application/xml; charset=utf-8" };
