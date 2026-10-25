import "./env";
import ratePairsJson from "./data/rate_pairs.json";

export const MAJOR_COLUMNS = ["USD", "EUR", "JPY", "GBP", "CNY", "VND"];
export const HOME_ROWS = [
  "USD", "EUR", "JPY", "GBP", "CNY", "KRW", "SGD", "THB", "VND",
  "AUD", "CAD", "CHF", "HKD", "INR", "IDR", "MYR", "PHP", "TWD", "NZD",
];
export const HOME_CHART_BASES = ["USD", "EUR", "JPY", "GBP", "CNY", "VND"];
export const CONVERTER_TARGETS = [
  "VND", "USD", "EUR", "JPY", "GBP", "CNY", "KRW", "THB", "SGD",
  "AUD", "CAD", "CHF", "HKD", "INR", "IDR", "MYR", "PHP", "TWD", "NZD",
];

export const MENU_GROUPS: Record<string, string[]> = {
  USD: ["VND", "EUR", "JPY", "GBP", "CNY", "KRW", "THB", "SGD"],
  EUR: ["USD", "VND", "GBP", "JPY", "CHF", "CNY"],
  JPY: ["USD", "VND", "EUR", "KRW", "CNY", "THB"],
  GBP: ["USD", "EUR", "VND", "JPY", "AUD", "CAD"],
  CNY: ["USD", "VND", "JPY", "EUR", "KRW", "THB"],
  VND: ["USD", "EUR", "JPY", "KRW", "THB", "CNY"],
};

export type CurrencyProfile = {
  name: string;
  region: string;
  role: string;
  use: string;
};

export const CURRENCY_PROFILES: Record<string, CurrencyProfile> = {
  USD: { name: "US dollar", region: "United States", role: "global reserve and settlement currency", use: "international pricing, cards, transfers, and dollar-linked invoices" },
  EUR: { name: "euro", region: "Euro Area", role: "major European currency", use: "European travel, trade, tuition, and cross-border payments" },
  JPY: { name: "Japanese yen", region: "Japan", role: "major Asian safe-haven currency", use: "Japan travel, business expenses, tuition, and import pricing" },
  GBP: { name: "British pound", region: "United Kingdom", role: "major sterling currency", use: "UK travel, education, invoices, and portfolio comparison" },
  CNY: { name: "Chinese yuan", region: "China", role: "major Asian trade currency", use: "China trade, sourcing, ecommerce costs, and regional currency comparison" },
  VND: { name: "Vietnamese dong", region: "Vietnam", role: "local Vietnamese currency", use: "Vietnam travel, salary conversion, remittance checks, and local price comparison" },
  KRW: { name: "South Korean won", region: "South Korea", role: "North Asian currency", use: "Korea travel, electronics trade, tuition, and regional comparisons" },
  THB: { name: "Thai baht", region: "Thailand", role: "Southeast Asian currency", use: "Thailand travel, tourism spending, and regional price checks" },
  SGD: { name: "Singapore dollar", region: "Singapore", role: "regional financial hub currency", use: "Singapore travel, business settlement, and Southeast Asia comparisons" },
  AUD: { name: "Australian dollar", region: "Australia", role: "commodity-linked major currency", use: "Australia travel, study, trade, and commodity-sensitive comparisons" },
  CAD: { name: "Canadian dollar", region: "Canada", role: "commodity-linked North American currency", use: "Canada travel, invoices, study, and oil-sensitive currency checks" },
  CHF: { name: "Swiss franc", region: "Switzerland", role: "traditional safe-haven currency", use: "Swiss travel, wealth references, and defensive currency comparison" },
  HKD: { name: "Hong Kong dollar", region: "Hong Kong", role: "USD-linked financial-market currency", use: "Hong Kong travel, business costs, and USD-linked rate checks" },
  INR: { name: "Indian rupee", region: "India", role: "large emerging-market currency", use: "India travel, outsourcing costs, remittances, and trade comparison" },
  IDR: { name: "Indonesian rupiah", region: "Indonesia", role: "Southeast Asian currency with large nominal values", use: "Indonesia travel, ecommerce, tourism, and local price conversion" },
  MYR: { name: "Malaysian ringgit", region: "Malaysia", role: "Southeast Asian currency", use: "Malaysia travel, trade, education, and regional price comparison" },
  PHP: { name: "Philippine peso", region: "Philippines", role: "Southeast Asian remittance currency", use: "Philippines travel, remittances, salaries, and local price checks" },
  TWD: { name: "Taiwan dollar", region: "Taiwan", role: "North Asian technology-sector currency", use: "Taiwan travel, electronics supply-chain costs, and regional comparisons" },
  NZD: { name: "New Zealand dollar", region: "New Zealand", role: "commodity-linked Pacific currency", use: "New Zealand travel, study, agriculture-linked pricing, and portfolio comparison" },
};

export function currencyProfile(code: string): CurrencyProfile {
  return CURRENCY_PROFILES[code] ?? { name: code, region: code, role: "currency", use: "currency conversion and comparison" };
}

function normalizePairs(pairs: unknown[]): [string, string][] {
  const out: [string, string][] = [];
  for (const pair of pairs) {
    let base: string;
    let target: string;
    if (typeof pair === "string") {
      const parts = pair.replace("-", "_").toUpperCase().split("_");
      if (parts.length !== 2) continue;
      [base, target] = parts;
    } else {
      const [b, t] = pair as [string, string];
      base = String(b).toUpperCase();
      target = String(t).toUpperCase();
    }
    if (base !== target && !out.some(([b, t]) => b === base && t === target)) {
      out.push([base, target]);
    }
  }
  return out;
}

export const RATE_PAIRS: [string, string][] = normalizePairs((ratePairsJson as { pairs: string[] }).pairs);

// Both derive from RATE_PAIRS, which is frozen at import time — so they are
// computed once rather than on every call. They sit on hot paths that call
// them per currency and per pair (buildQuoteRateRows, loadPairEntries), where
// rebuilding the Set/array each time was pure waste.
let pairKeysCache: Set<string> | null = null;
let currenciesCache: readonly string[] | null = null;

export function configuredPairKeys(): Set<string> {
  if (!pairKeysCache) {
    pairKeysCache = new Set(RATE_PAIRS.map(([base, target]) => pairKey(base, target)));
  }
  return pairKeysCache;
}

/** Shared, and therefore read-only: callers filter or map it, never mutate it. */
export function configCurrencies(): readonly string[] {
  if (currenciesCache) return currenciesCache;
  const currencies: string[] = [];
  for (const [base, target] of RATE_PAIRS) {
    if (!currencies.includes(base)) currencies.push(base);
    if (!currencies.includes(target)) currencies.push(target);
  }
  const idx = currencies.indexOf("USD");
  if (idx > 0) {
    currencies.splice(idx, 1);
    currencies.unshift("USD");
  }
  currenciesCache = Object.freeze(currencies);
  return currenciesCache;
}

export function pairKey(base: string, target: string): string {
  return `${base.toLowerCase()}_${target.toLowerCase()}`;
}

/**
 * Every pair page the site serves, deduplicated. Three sources:
 *
 *  - the stored pairs, which are all quoted against USD (EUR/USD, MYR/USD…)
 *  - the reverse of each stored pair (USD/EUR, USD/MYR…)
 *  - the hand-picked menu pairs, which include derived pairs with no stored
 *    file of their own
 *
 * The reverses matter: a pair page has always answered in both directions,
 * and Google had already indexed several of them — /usd-myr and /usd-idr were
 * ranking while appearing in no sitemap at all, found by following the links
 * in the converter and the menu. They were real pages the site simply never
 * declared.
 *
 * This is deliberately not "every combination": any two configured currencies
 * make a valid URL, which is 700-odd pages, and most of them nobody asks for.
 * Stored data in both directions, plus the curated set, is the line.
 *
 * Used by the analysis index, which links every one of them — a page kept out
 * of search still works for a reader. The sitemap lists CANONICAL_PAIRS only.
 */
let allPairsCache: [string, string][] | null = null;

export function allPairs(): readonly [string, string][] {
  if (allPairsCache) return allPairsCache;
  const seen = new Set<string>();
  const out: [string, string][] = [];
  for (const [base, target] of [
    ...RATE_PAIRS,
    ...RATE_PAIRS.map(([base, target]) => [target, base] as [string, string]),
    ...Object.entries(MENU_GROUPS).flatMap(([base, targets]) =>
      targets.filter((target) => target !== base).map((target) => [base, target] as [string, string])),
  ]) {
    const key = pairKey(base, target);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push([base, target]);
  }
  allPairsCache = out;
  return out;
}

/** Currencies that head at least one pair page, in configCurrencies() order. */
export function currenciesWithPairs(): string[] {
  const bases = new Set(allPairs().map(([base]) => base));
  return configCurrencies().filter((code) => bases.has(code));
}

export function pairsForBase(base: string): [string, string][] {
  const code = base.toUpperCase();
  return allPairs().filter(([pairBase]) => pairBase === code) as [string, string][];
}

// Every pair page is built from one template in lib/pair.ts: the numbers,
// chart and statistics are genuinely per-pair, but the prose around them is
// the same sentences with the currency names swapped. Ad networks and Google's
// own spam policy call that scaled content, and hundreds of near-identical
// pages submitted at once is what gets a site rejected.
//
// So only pairs between the core currencies below are put forward for
// indexing, and only in one direction each: the reverse direction carries a
// canonical pointing at it (and no noindex — the two together send Google
// contradictory signals). Every pair outside the core still renders for
// visitors but carries `noindex,follow` and stays out of sitemap.xml.
// robots.txt must not block those pages: a crawler that cannot fetch a page
// never sees its noindex.

/** The only currencies whose pairs are offered for indexing. */
export const INDEXABLE_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "VND", "CNY"] as const;

/**
 * The indexable direction of each core pair, quoted the way the market quotes
 * it (EUR before GBP before USD before CNY before JPY before VND). These are
 * the pair URLs in sitemap.xml. The reverse direction (/vnd-usd, /usd-eur…)
 * still renders, and names its counterpart here as canonical.
 *
 * Must hold every pairing of INDEXABLE_CURRENCIES exactly once, which is
 * checked below: adding a currency without its pairs fails at import, so in
 * `npm run build` (scripts/check-sitemap.mjs) rather than in production.
 */
export const CANONICAL_PAIRS: readonly (readonly [string, string])[] = [
  ["EUR", "USD"], ["GBP", "USD"], ["USD", "JPY"], ["USD", "CNY"],
  ["USD", "VND"], ["EUR", "VND"], ["GBP", "VND"], ["JPY", "VND"], ["CNY", "VND"],
  ["EUR", "GBP"], ["EUR", "JPY"], ["EUR", "CNY"], ["GBP", "JPY"], ["GBP", "CNY"], ["CNY", "JPY"],
];

{
  const core = new Set<string>(INDEXABLE_CURRENCIES);
  const pairings = new Set(CANONICAL_PAIRS.map(([base, target]) => [base, target].sort().join("_")));
  const expected = (core.size * (core.size - 1)) / 2;
  const stray = CANONICAL_PAIRS.filter(([base, target]) => base === target || !core.has(base) || !core.has(target));
  if (stray.length || pairings.size !== CANONICAL_PAIRS.length || pairings.size !== expected) {
    throw new Error(
      `CANONICAL_PAIRS must list each of the ${expected} pairings of INDEXABLE_CURRENCIES exactly once`
      + ` (has ${CANONICAL_PAIRS.length}, ${pairings.size} distinct${stray.length ? `, stray: ${stray.map((p) => p.join("/")).join(", ")}` : ""})`,
    );
  }
}

const canonicalPairKeys = new Set(CANONICAL_PAIRS.map(([base, target]) => pairKey(base, target)));

/** True for the 15 pair pages offered for indexing, in their canonical direction only. */
export function pairIsIndexable(base: string, target: string): boolean {
  return canonicalPairKeys.has(pairKey(base, target));
}

/**
 * The canonical direction of a pair between two core currencies — the pair
 * itself or its reverse — or null when either currency is outside the core,
 * in which case the page is its own canonical.
 */
export function canonicalPair(base: string, target: string): [string, string] | null {
  if (canonicalPairKeys.has(pairKey(base, target))) return [base, target];
  if (canonicalPairKeys.has(pairKey(target, base))) return [target, base];
  return null;
}

/**
 * noindex only outside the core. A reverse-direction core page (/vnd-usd) is
 * left indexable and relies on its canonical alone.
 */
export function pairIsNoindex(base: string, target: string): boolean {
  return canonicalPair(base, target) === null;
}

/**
 * Canonical pairs to link from a pair page: those sharing a currency with it,
 * then the rest, never the page itself or its reverse. Only canonical pairs,
 * so every related link is a page that is in the sitemap.
 */
export function relatedCanonicalPairs(base: string, target: string, limit = 6): [string, string][] {
  const own = canonicalPair(base, target);
  const others = CANONICAL_PAIRS.filter(([b, t]) => !own || pairKey(b, t) !== pairKey(own[0], own[1]));
  const shares = ([b, t]: readonly [string, string]) => [b, t].some((code) => code === base || code === target);
  return [...others.filter(shares), ...others.filter((pair) => !shares(pair))]
    .slice(0, limit)
    .map(([b, t]) => [b, t]);
}

export function pairUrl(base: string, target: string): string {
  return `/${base.toLowerCase()}-${target.toLowerCase()}`;
}

/** `/vnd` — the hub every `/vnd-*` and `/*-vnd` pair page hangs under. */
export function currencyUrl(code: string): string {
  return `/${code.toLowerCase()}`;
}

export function isCurrencyCode(code: string): boolean {
  return configCurrencies().includes(code.toUpperCase());
}

export function parsePairKey(pair: string): [string, string] {
  const parts = pair.replace("-", "_").toUpperCase().split("_");
  if (parts.length !== 2 || !parts[0] || !parts[1]) {
    throw new Error(`Invalid pair ${pair}; expected BASE_TARGET, e.g. vnd_usd`);
  }
  return [parts[0], parts[1]];
}
