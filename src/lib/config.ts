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

// Every pair page is built from one template in lib/pair.ts: the numbers,
// chart and statistics are genuinely per-pair, but the prose around them is
// the same sentences with the currency names swapped. Ad networks and Google's
// own spam policy call that scaled content, and 59 near-identical pages
// submitted at once is what gets a site rejected.
//
// The 38 pairs reachable from the header menu are the hand-picked ones people
// actually search for. The rest exist because the fetcher stores a file for
// every currency against USD -- AED/USD, IDR/USD and friends -- and they are
// pure long tail.
//
// Turning NOINDEX_LONGTAIL_PAIRS on marks that long tail `noindex` and drops
// it from the sitemap, leaving 38 curated pages for review. It is OFF by
// default: removing pages from an index is not something that should happen as
// a side effect of a deploy. Turn it off again once those pages carry writing
// of their own.
/**
 * Every pair page the site serves, deduplicated: the stored pairs plus the
 * hand-picked menu ones, which include derived pairs with no stored file.
 * Shared by the sitemap (which then drops the noindexed ones) and the analysis
 * index (which does not — a page kept out of search still works for a reader).
 */
let allPairsCache: [string, string][] | null = null;

export function allPairs(): readonly [string, string][] {
  if (allPairsCache) return allPairsCache;
  const seen = new Set<string>();
  const out: [string, string][] = [];
  for (const [base, target] of [
    ...RATE_PAIRS,
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

let featuredPairsCache: Set<string> | null = null;

export function featuredPairKeys(): Set<string> {
  if (!featuredPairsCache) {
    featuredPairsCache = new Set(
      Object.entries(MENU_GROUPS).flatMap(([base, targets]) =>
        targets.filter((target) => target !== base).map((target) => pairKey(base, target))),
    );
  }
  return featuredPairsCache;
}

const NOINDEX_LONGTAIL = ["1", "true", "yes", "on"]
  .includes((process.env.NOINDEX_LONGTAIL_PAIRS ?? "").trim().toLowerCase());

/** True when this pair page should ask search engines not to index it. */
export function pairIsNoindex(base: string, target: string): boolean {
  return NOINDEX_LONGTAIL && !featuredPairKeys().has(pairKey(base, target));
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
