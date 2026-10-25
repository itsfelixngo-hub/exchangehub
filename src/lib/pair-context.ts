import { CANONICAL_PAIRS, canonicalPair, pairKey } from "./config";

/**
 * Background on the two currencies of each canonical pair: 2-3 sentences,
 * written by the site owner rather than generated, because it is the one part
 * of a pair page that cannot come from the rate data.
 *
 * A pair page shows its entry only once it is filled in. Leave an entry as ""
 * until the text exists — an empty string renders nothing, so a half-finished
 * table never puts placeholder text in front of a reader. Keys are
 * `base_target` in the canonical direction (CANONICAL_PAIRS in config.ts); the
 * reverse page (/vnd-usd) shows its canonical pair's text.
 */
export const PAIR_CONTEXT: Record<string, string> = {
  eur_usd: "", // TODO: background on the euro and the US dollar
  gbp_usd: "", // TODO: background on the British pound and the US dollar
  usd_jpy: "", // TODO: background on the US dollar and the Japanese yen
  usd_cny: "", // TODO: background on the US dollar and the Chinese yuan
  usd_vnd: "", // TODO: background on the US dollar and the Vietnamese dong
  eur_vnd: "", // TODO: background on the euro and the Vietnamese dong
  gbp_vnd: "", // TODO: background on the British pound and the Vietnamese dong
  jpy_vnd: "", // TODO: background on the Japanese yen and the Vietnamese dong
  cny_vnd: "", // TODO: background on the Chinese yuan and the Vietnamese dong
  eur_gbp: "", // TODO: background on the euro and the British pound
  eur_jpy: "", // TODO: background on the euro and the Japanese yen
  eur_cny: "", // TODO: background on the euro and the Chinese yuan
  gbp_jpy: "", // TODO: background on the British pound and the Japanese yen
  gbp_cny: "", // TODO: background on the British pound and the Chinese yuan
  cny_jpy: "", // TODO: background on the Chinese yuan and the Japanese yen
};

{
  const expected = new Set(CANONICAL_PAIRS.map(([base, target]) => pairKey(base, target)));
  const keys = Object.keys(PAIR_CONTEXT);
  const missing = [...expected].filter((key) => !keys.includes(key));
  const stray = keys.filter((key) => !expected.has(key));
  if (missing.length || stray.length) {
    throw new Error(`PAIR_CONTEXT must have one entry per canonical pair (missing: ${missing.join(", ") || "none"}; not canonical: ${stray.join(", ") || "none"})`);
  }
}

/** The owner-written background for a core pair, or null while it is unwritten. */
export function pairContext(base: string, target: string): string | null {
  const canonical = canonicalPair(base, target);
  if (!canonical) return null;
  const text = (PAIR_CONTEXT[pairKey(canonical[0], canonical[1])] ?? "").trim();
  return text || null;
}

/**
 * Who issues each core currency and how its exchange rate is set. Used by the
 * pair FAQ; deliberately limited to facts that do not date — no rates, no
 * band widths, no member counts.
 */
export type CurrencyFacts = {
  /** "the US dollar" — the name as it reads mid-sentence. */
  name: string;
  centralBank: string;
  economy: string;
  /** Floating currencies move with the market; managed ones trade around an official daily rate. */
  regime: "floating" | "managed";
  /** One clause on how the rate is set, for the managed currencies. */
  regimeNote?: string;
};

export const CURRENCY_FACTS: Record<string, CurrencyFacts> = {
  USD: { name: "the US dollar", centralBank: "the Federal Reserve", economy: "the United States", regime: "floating" },
  EUR: { name: "the euro", centralBank: "the European Central Bank", economy: "the euro area", regime: "floating" },
  GBP: { name: "the British pound", centralBank: "the Bank of England", economy: "the United Kingdom", regime: "floating" },
  JPY: { name: "the Japanese yen", centralBank: "the Bank of Japan", economy: "Japan", regime: "floating" },
  CNY: {
    name: "the Chinese yuan",
    centralBank: "the People's Bank of China",
    economy: "China",
    regime: "managed",
    regimeNote: "the onshore yuan trades within a band around a central parity rate the People's Bank of China sets each morning",
  },
  VND: {
    name: "the Vietnamese dong",
    centralBank: "the State Bank of Vietnam",
    economy: "Vietnam",
    regime: "managed",
    regimeNote: "the dong trades within a band around a central rate the State Bank of Vietnam publishes every business day",
  },
};
