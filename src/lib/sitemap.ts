import { CANONICAL_PAIRS, INDEXABLE_CURRENCIES, canonicalPair, pairUrl } from "./config";
import { INFO_LINKS, INFO_CONTENT_LAST_MODIFIED } from "./info";
import { buildLatestUsdTable } from "./rates";

/**
 * `/sitemap.xml` is a single urlset holding exactly the pages the site asks to
 * have indexed: the home page, the five info pages, and the 15 core pairs in
 * their canonical direction (CANONICAL_PAIRS in src/lib/config.ts). Nothing
 * else — the currency hubs, /analysis, /chart and every other pair page still
 * answer and are linked from every page, but they are not submitted.
 *
 * It used to be an index over three sections with every pair in both
 * directions. That put ~80 pages from one template in front of a reviewer;
 * twenty is a sitemap a person can read in full.
 *
 * scripts/check-sitemap.mjs runs sitemapEntries() before every build and
 * fails it if a non-core pair, or anything outside the list above, appears.
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

/** Every URL in sitemap.xml. Synchronous and free of I/O, so the build check can call it. */
export function sitemapEntries(dataDay: string): SitemapEntry[] {
  return [
    { path: "/", lastmod: dataDay },
    ...INFO_LINKS.map((link) => ({ path: link.href, lastmod: INFO_CONTENT_LAST_MODIFIED })),
    ...CANONICAL_PAIRS.map(([base, target]) => ({ path: pairUrl(base, target), lastmod: dataDay })),
  ];
}

const PAIR_PATH = /^\/([a-z]{3})-([a-z]{3})$/;

/**
 * Why each entry does not belong in the sitemap; empty when all of them do.
 * A pair belongs only between two core currencies and in its canonical
 * direction; any other path only if it is the home page or an info page.
 */
export function sitemapProblems(entries: SitemapEntry[]): string[] {
  const core = new Set<string>(INDEXABLE_CURRENCIES);
  const pages = new Set(["/", ...INFO_LINKS.map((link) => link.href)]);
  const problems: string[] = [];
  const seen = new Set<string>();
  for (const { path } of entries) {
    if (seen.has(path)) problems.push(`${path} is listed twice`);
    seen.add(path);
    const pair = path.match(PAIR_PATH);
    if (pair) {
      const base = pair[1].toUpperCase();
      const target = pair[2].toUpperCase();
      if (!core.has(base) || !core.has(target)) {
        problems.push(`${path} is not a pair between ${INDEXABLE_CURRENCIES.join(", ")}`);
      } else {
        const canonical = canonicalPair(base, target);
        if (canonical && (canonical[0] !== base || canonical[1] !== target)) {
          problems.push(`${path} is the reverse of ${pairUrl(canonical[0], canonical[1])}`);
        }
      }
    } else if (!pages.has(path)) {
      problems.push(`${path} is neither a core pair, the home page nor an info page`);
    }
  }
  return problems;
}

export function renderUrlset(origin: string, entries: SitemapEntry[]): string {
  return `<?xml version="1.0" encoding="UTF-8"?>\n`
    + `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n`
    + entries.map(({ path, lastmod }) =>
        `  <url><loc>${escapeXml(origin + path)}</loc><lastmod>${lastmod}</lastmod></url>`).join("\n")
    + `\n</urlset>\n`;
}

export const XML_HEADERS = { "content-type": "application/xml; charset=utf-8" };
