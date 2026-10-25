import { configuredPairKeys, currencyProfile, pairKey } from "./config";
import { CURRENCY_FACTS } from "./pair-context";
import { pairHistory, type RateEntry } from "./rates";

/** "the euro" — the currency as it reads mid-sentence. */
function currencyFactsName(code: string): string {
  return CURRENCY_FACTS[code]?.name ?? `the ${currencyProfile(code).name}`;
}

/**
 * The written part of a canonical pair page — summary, FAQ, method note —
 * built from the stored rates rather than from one paragraph with the currency
 * names swapped. Every sentence is chosen by what the data did: which way it
 * moved and how far, how wide the week's range was, where the latest rate sits
 * in it, how the daily closes went, and (for a cross pair) which of the two
 * currencies did the moving against the dollar. Two pairs that had different
 * weeks read differently.
 *
 * Only stored data is used. The fetcher keeps about a week of five-minute
 * points (MAX_ENTRIES_PER_PAIR in modules/exchange_rates/fetch_rates.py), so
 * the window is 7 days and the copy says so; nothing here may claim a longer
 * period than the data covers.
 */

export const WINDOW_DAYS = 7;
const WINDOW_SECONDS = WINDOW_DAYS * 24 * 3600;
const DAY_SECONDS = 24 * 3600;

/** Shown on the page next to every statistic, and named in About/Disclaimer. */
export const DATA_SOURCE = { name: "Open Exchange Rates", url: "https://openexchangerates.org/" } as const;

export type WindowStats = {
  high: number;
  low: number;
  average: number;
  first: number;
  latest: number;
  changePct: number;
  /** (high - low) / average, in percent. */
  rangePct: number;
  /** Where the latest rate sits between the low (0) and the high (1). */
  position: number;
  points: number;
  fromTs: number;
  toTs: number;
  /** Days actually covered, which is under 7 only when stored history is. */
  coveredDays: number;
  /** Daily closes compared with the close before. */
  upDays: number;
  downDays: number;
  comparedDays: number;
  biggestDay: { ts: number; pct: number } | null;
};

/** Statistics over the last WINDOW_DAYS of stored history; null with fewer than two points. */
export function windowStats(history: RateEntry[], seconds = WINDOW_SECONDS): WindowStats | null {
  const usable = history.filter((entry) => Number.isFinite(Number(entry.rate)) && Number(entry.rate) > 0);
  if (usable.length < 2) return null;
  const newest = usable[usable.length - 1].ts;
  const points = usable.filter((entry) => entry.ts >= newest - seconds);
  if (points.length < 2) return null;

  let high = -Infinity;
  let low = Infinity;
  let sum = 0;
  for (const { rate } of points) {
    const value = Number(rate);
    if (value > high) high = value;
    if (value < low) low = value;
    sum += value;
  }
  const first = Number(points[0].rate);
  const latest = Number(points[points.length - 1].rate);
  const average = sum / points.length;

  // Daily closes: the last stored rate of each UTC day in the window.
  const closes = new Map<number, { ts: number; rate: number }>();
  for (const entry of points) {
    closes.set(Math.floor(entry.ts / DAY_SECONDS), { ts: entry.ts, rate: Number(entry.rate) });
  }
  const daily = [...closes.values()];
  let upDays = 0;
  let downDays = 0;
  let biggestDay: WindowStats["biggestDay"] = null;
  for (let i = 1; i < daily.length; i++) {
    const pct = ((daily[i].rate - daily[i - 1].rate) / daily[i - 1].rate) * 100;
    if (pct > 0.005) upDays++;
    else if (pct < -0.005) downDays++;
    if (!biggestDay || Math.abs(pct) > Math.abs(biggestDay.pct)) biggestDay = { ts: daily[i].ts, pct };
  }

  return {
    high, low, average, first, latest,
    changePct: ((latest - first) / first) * 100,
    rangePct: average ? ((high - low) / average) * 100 : 0,
    position: high > low ? (latest - low) / (high - low) : 0.5,
    points: points.length,
    fromTs: points[0].ts,
    toTs: newest,
    coveredDays: (newest - points[0].ts) / DAY_SECONDS,
    upDays, downDays,
    comparedDays: Math.max(0, daily.length - 1),
    biggestDay,
  };
}

/** Each currency's move against the US dollar over the same window (USD itself is 0). */
export type LegMoves = { base: number; target: number };

async function moveAgainstUsd(code: string): Promise<number | null> {
  if (code === "USD") return 0;
  // Stored as CODE/USD, so a rising rate means the currency gained on the dollar.
  const stats = windowStats(await pairHistory(code, "USD"));
  return stats ? stats.changePct : null;
}

export async function legMoves(base: string, target: string): Promise<LegMoves | null> {
  const [b, t] = await Promise.all([moveAgainstUsd(base), moveAgainstUsd(target)]);
  return b === null || t === null ? null : { base: b, target: t };
}

/**
 * A rate as it reads in a sentence. The tables and tiles keep formatRate's
 * full precision; prose stops at four or five significant figures, because
 * "0.83771447" in the middle of a sentence is noise.
 */
export function proseRate(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1000) return value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (abs >= 100) return value.toFixed(2);
  if (abs >= 1) return value.toFixed(4);
  return String(Number(value.toPrecision(4)));
}

const pct = (value: number, digits = 2) => `${Math.abs(value).toFixed(digits)}%`;
const signed = (value: number, digits = 2) => `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(digits)}%`;

function utcDay(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
}

function windowLabel(stats: WindowStats): string {
  // Short of six days only when stored history is — say what was covered
  // rather than call it a week.
  if (stats.coveredDays >= 6) return `the last ${WINDOW_DAYS} days`;
  const days = Math.max(1, Math.round(stats.coveredDays));
  return days === 1 ? "the last day of stored data" : `the last ${days} days of stored data`;
}

type MoveSize = "flat" | "small" | "clear" | "large";
function moveSize(changePct: number): MoveSize {
  const size = Math.abs(changePct);
  if (size < 0.1) return "flat";
  if (size < 0.5) return "small";
  if (size < 1.5) return "clear";
  return "large";
}

type Volatility = "calm" | "moderate" | "choppy";
function volatility(rangePct: number): Volatility {
  if (rangePct < 0.4) return "calm";
  if (rangePct < 1.5) return "moderate";
  return "choppy";
}

/**
 * The summary paragraph. Sentences are picked independently on five axes, so
 * the paragraph's shape — not just its numbers — follows the data.
 */
export function buildSummary(base: string, target: string, stats: WindowStats | null, legs: LegMoves | null): string {
  const b = currencyFactsName(base);
  const t = currencyFactsName(target);
  if (!stats) {
    return `There is not yet enough stored history to describe how ${b} has moved against ${t}; the statistics fill in as new rates are recorded.`;
  }
  const latest = proseRate(stats.latest);
  const high = proseRate(stats.high);
  const low = proseRate(stats.low);
  const span = windowLabel(stats);
  const size = moveSize(stats.changePct);
  const up = stats.changePct > 0;
  const sentences: string[] = [];

  // 1. Direction and size of the move.
  if (size === "flat") {
    sentences.push(`Over ${span} ${b} has barely moved against ${t}: at ${latest}, ${base}/${target} is within ${pct(stats.changePct)} of where the period began.`);
  } else if (size === "small") {
    sentences.push(up
      ? `${capitalise(b)} edged up against ${t} over ${span}, a gain of ${pct(stats.changePct)} that leaves 1 ${base} at ${latest} ${target}.`
      : `${capitalise(b)} slipped against ${t} over ${span}, losing ${pct(stats.changePct)} to stand at ${latest} ${target}.`);
  } else if (size === "clear") {
    sentences.push(up
      ? `${capitalise(b)} rose ${pct(stats.changePct)} against ${t} over ${span}, taking ${base}/${target} from ${proseRate(stats.first)} to ${latest}.`
      : `${capitalise(b)} fell ${pct(stats.changePct)} against ${t} over ${span}, taking ${base}/${target} from ${proseRate(stats.first)} to ${latest}.`);
  } else {
    sentences.push(up
      ? `It has been a strong stretch for ${b}: ${base}/${target} climbed ${pct(stats.changePct)} over ${span} and now trades at ${latest}.`
      : `${capitalise(b)} lost significant ground over ${span}: ${base}/${target} dropped ${pct(stats.changePct)} and now trades at ${latest}.`);
  }

  // 2. How wide the range was.
  const vol = volatility(stats.rangePct);
  if (vol === "calm") {
    sentences.push(`Trading was quiet, with only ${pct(stats.rangePct)} between the period's high of ${high} and low of ${low}.`);
  } else if (vol === "moderate") {
    sentences.push(`The rate moved between ${low} and ${high}, a range of ${pct(stats.rangePct)} of its average.`);
  } else {
    sentences.push(`Price action was choppy, swinging across a ${pct(stats.rangePct)} range from ${low} up to ${high}.`);
  }

  // 3. Where the latest rate sits in that range.
  if (vol !== "calm" || size !== "flat") {
    if (stats.position >= 0.8) {
      sentences.push(up
        ? "The latest quote is close to the top of that range, so the gain was holding at the most recent update."
        : "Despite the decline, the latest quote has recovered to near the top of the range.");
    } else if (stats.position <= 0.2) {
      sentences.push(up
        ? "Even after the gain, the latest quote has pulled back to near the bottom of the range."
        : "The latest quote is near the bottom of the range, with no meaningful rebound yet.");
    } else {
      const above = stats.latest >= stats.average;
      sentences.push(`At ${latest} the rate sits mid-range, slightly ${above ? "above" : "below"} the ${WINDOW_DAYS}-day average of ${proseRate(stats.average)}.`);
    }
  }

  // 4. Daily closes and the biggest single day.
  if (stats.comparedDays >= 4) {
    const { upDays, downDays, comparedDays, biggestDay } = stats;
    const unchanged = comparedDays - upDays - downDays;
    const rest = unchanged ? ` (${unchanged} unchanged)` : "";
    let days: string;
    if (upDays >= 3 && upDays > 2 * downDays) days = `of the last ${comparedDays} daily closes, ${upDays} were higher than the day before${rest}`;
    else if (downDays >= 3 && downDays > 2 * upDays) days = `of the last ${comparedDays} daily closes, ${downDays} were lower than the day before${rest}`;
    else days = `daily closes were mixed: ${upDays} up, ${downDays} down${unchanged ? `, ${unchanged} unchanged` : ""} out of ${comparedDays}`;
    const biggest = biggestDay && Math.abs(biggestDay.pct) >= 0.05
      ? `; the largest one-day move was ${signed(biggestDay.pct)} on ${utcDay(biggestDay.ts)}`
      : "";
    sentences.push(`${capitalise(days)}${biggest}.`);
  }

  // 5. For a cross pair, which side did the moving against the dollar.
  if (legs && base !== "USD" && target !== "USD" && size !== "flat") {
    const bMove = legs.base;
    const tMove = legs.target;
    const verb = (move: number) => (move >= 0 ? "gained" : "lost");
    if (Math.abs(bMove) >= 2 * Math.abs(tMove)) {
      sentences.push(`Most of the move came from ${b}, which ${verb(bMove)} ${pct(bMove)} against the US dollar while ${t} changed by just ${signed(tMove)}.`);
    } else if (Math.abs(tMove) >= 2 * Math.abs(bMove)) {
      sentences.push(`${capitalise(t)} did most of the moving: it ${verb(tMove)} ${pct(tMove)} against the US dollar, compared with ${signed(bMove)} for ${b}.`);
    } else if (Math.sign(bMove) === Math.sign(tMove)) {
      sentences.push(`Both currencies moved the same way against the US dollar (${signed(bMove)} and ${signed(tMove)}), which kept the cross rate's move smaller than either.`);
    } else {
      sentences.push(`The two currencies went opposite ways against the US dollar — ${b} ${signed(bMove)}, ${t} ${signed(tMove)} — which is what widened the move in ${base}/${target}.`);
    }
  }

  return sentences.join(" ");
}

export type Faq = { question: string; answer: string };

/**
 * Four questions: two answered from the data, two from what is particular to
 * the pair (who issues each currency and how its rate is set). Which questions
 * appear depends on the pair, not only their wording.
 */
export function buildFaqs(base: string, target: string, stats: WindowStats | null, legs: LegMoves | null): Faq[] {
  const bf = CURRENCY_FACTS[base];
  const tf = CURRENCY_FACTS[target];
  const b = currencyFactsName(base);
  const t = currencyFactsName(target);
  const faqs: Faq[] = [];

  // Data: the move over the window.
  if (stats) {
    const size = moveSize(stats.changePct);
    const span = windowLabel(stats);
    const answer = size === "flat"
      ? `Very little. Over ${span} ${base}/${target} changed by ${signed(stats.changePct)}, and the gap between the high (${proseRate(stats.high)}) and the low (${proseRate(stats.low)}) was ${pct(stats.rangePct)}.`
      : `${base}/${target} ${stats.changePct > 0 ? "rose" : "fell"} ${pct(stats.changePct)} over ${span}, trading between ${proseRate(stats.low)} and ${proseRate(stats.high)}. `
        + (stats.changePct > 0 ? `In other words, ${b} bought more ${target} at the end of the period than at the start.` : `In other words, ${b} bought less ${target} at the end of the period than at the start.`);
    faqs.push({ question: `How much has ${base}/${target} moved in the last ${WINDOW_DAYS} days?`, answer });

    // Data: is today's rate high or low for the week?
    const where = stats.position >= 0.8 ? "near the top" : stats.position <= 0.2 ? "near the bottom" : "in the middle";
    faqs.push({
      question: `Is 1 ${base} = ${proseRate(stats.latest)} ${target} high or low for the past week?`,
      answer: `It is ${where} of the last ${WINDOW_DAYS} days' range of ${proseRate(stats.low)} to ${proseRate(stats.high)}, and ${stats.latest >= stats.average ? "above" : "below"} the ${WINDOW_DAYS}-day average of ${proseRate(stats.average)}. `
        + "A week of data says nothing about where the rate goes next; it only places today's quote in recent context.",
    });
  } else {
    faqs.push({
      question: `How much has ${base}/${target} moved recently?`,
      answer: "Not enough history is stored yet to say. The figure appears once a few days of rates have been recorded.",
    });
  }

  // Pair-specific: who stands behind each currency.
  if (bf && tf) {
    faqs.push({
      question: `Which central banks are behind ${base} and ${target}?`,
      answer: `${capitalise(b)} is issued by ${bf.centralBank} for ${bf.economy}, and ${t} by ${tf.centralBank} for ${tf.economy}. `
        + `Interest-rate decisions and statements from ${bf.centralBank} and ${tf.centralBank} are among the main things that move this pair.`,
    });
  }

  // Pair-specific: what kind of pair it is.
  const managed = [bf, tf].filter((facts): facts is NonNullable<typeof facts> => facts?.regime === "managed");
  if (managed.length === 2) {
    faqs.push({
      question: `Do both ${base} and ${target} trade freely?`,
      answer: `No. Both are managed currencies: ${managed[0].regimeNote}, and ${managed[1].regimeNote}. `
        + `The ${base}/${target} rate on this page is a cross rate worked out from each one's rate against the US dollar.`,
    });
  } else if (managed.length === 1) {
    // Only core pairs reach this function, and every core currency has facts.
    const managedFacts = managed[0];
    const managedCode = managedFacts === bf ? base : target;
    const freeCode = managedFacts === bf ? target : base;
    const free = (managedFacts === bf ? tf : bf)!;
    const managedMove = legs ? (managedFacts === bf ? legs.base : legs.target) : null;
    const freeMove = legs ? (managedFacts === bf ? legs.target : legs.base) : null;
    if (freeCode === "USD") {
      // USD/VND, USD/CNY: the managed side is the whole story.
      faqs.push({
        question: `How much is ${managedCode} allowed to move against the US dollar?`,
        answer: `Only within limits: ${managedFacts.regimeNote}. That is why ${base}/${target} tends to move in small steps rather than the swings of freely floating pairs`
          + (managedMove !== null ? `; over the last ${WINDOW_DAYS} days ${managedFacts.name} moved ${signed(managedMove)} against the dollar.` : "."),
      });
    } else {
      // GBP/VND, CNY/JPY…: the managed side stays close to the dollar, so the
      // pair mostly follows the free currency's own dollar rate.
      faqs.push({
        question: `Why does ${base}/${target} largely follow ${freeCode}/USD?`,
        answer: `Because ${managedFacts.regimeNote}, so ${managedFacts.name} stays close to the US dollar while ${free.name} floats freely. Most day-to-day movement in ${base}/${target} therefore comes from ${free.name}'s side`
          + (freeMove !== null && managedMove !== null
            ? `: over the last ${WINDOW_DAYS} days ${free.name} moved ${signed(freeMove)} against the dollar and ${managedFacts.name} ${signed(managedMove)}.`
            : "."),
      });
    }
  } else if (base === "USD" || target === "USD") {
    const other = (base === "USD" ? tf : bf)!;
    faqs.push({
      question: `Why is ${base}/${target} quoted with ${base} first?`,
      answer: `That is the market convention for this pair: it is quoted as ${target} per ${base}, so a rising number means ${b} is strengthening against ${t}. `
        + `${capitalise(other.name)} floats freely against the dollar, so the rate reflects supply and demand rather than an official fixing.`,
    });
  } else {
    faqs.push({
      question: `How is ${base}/${target} calculated if neither currency is the US dollar?`,
      answer: `Like most cross rates, it is derived from each currency's rate against the US dollar at the same moment: 1 ${base} = (${target} per USD) ÷ (${base} per USD). `
        + (legs ? `Over the last ${WINDOW_DAYS} days ${b} moved ${signed(legs.base)} against the dollar and ${t} ${signed(legs.target)}.` : ""),
    });
  }

  return faqs.slice(0, 4);
}

/** How the number on the page is produced, in one or two sentences. */
export function methodNote(base: string, target: string): string {
  const stored = configuredPairKeys().has(pairKey(base, target)) || configuredPairKeys().has(pairKey(target, base));
  if (base === "USD" || target === "USD" || stored) {
    return `${DATA_SOURCE.name} publishes every currency's mid-market rate against the US dollar. `
      + `This page uses that ${base}/${target} rate directly (inverted where the source quotes the other way round).`;
  }
  return `This is a cross rate. ${DATA_SOURCE.name} publishes each currency's mid-market rate against the US dollar, `
    + `and 1 ${base} is calculated as (${target} per USD) ÷ (${base} per USD) using both rates from the same update.`;
}

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
