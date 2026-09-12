import { currencyProfile, pairUrl } from "./config";
import { formatAmount, formatRate } from "./format";
import { downsamplePoints, type Point } from "./home";
import { pairHistory, type RateEntry } from "./rates";

const PAIR_CHART_MAX_POINTS = Number(process.env.PAIR_CHART_MAX_POINTS ?? "600");

export type PairStats = {
  points: number;
  high: number;
  low: number;
  average: number;
  first: number;
  latest: number;
  change: number;
  changePct: number;
  direction: "up" | "down" | "flat";
  updated: number | null;
};

export type PairModel = {
  base: string;
  target: string;
  history: RateEntry[];
  latest: RateEntry | null;
  rate: number | null;
  reverseRate: number | null;
  stats: PairStats | null;
  amounts: number[];
};

// Nominal size decides which ladder of amounts is worth printing: "1 VND"
// converts to a rounding error in every other currency, and "1,000,000 USD"
// is not a row anyone reads off a reference table.
export function pairAmounts(base: string): number[] {
  const highNominal = new Set(["VND", "IDR", "KRW"]);
  const mediumNominal = new Set(["JPY", "PHP", "TWD", "THB", "INR"]);
  if (highNominal.has(base)) return [1000, 5000, 10000, 50000, 100000, 500000, 1000000, 5000000, 10000000, 50000000];
  if (mediumNominal.has(base)) return [100, 500, 1000, 5000, 10000, 25000, 50000, 100000, 500000, 1000000];
  return [1, 5, 10, 25, 50, 100, 500, 1000, 5000, 10000];
}

export function statsFor(rates: number[], updated: number | null = null): PairStats | null {
  if (!rates.length) return null;
  const first = rates[0];
  const latest = rates[rates.length - 1];
  const change = latest - first;
  const changePct = first ? (change / first) * 100 : 0;
  // One pass, and no `Math.max(...rates)`: spreading the array passes every
  // point as a call argument, which throws RangeError once a stored history
  // outgrows the engine's argument limit (a few years of 5-minute points).
  let high = rates[0];
  let low = rates[0];
  let sum = 0;
  for (const rate of rates) {
    if (rate > high) high = rate;
    if (rate < low) low = rate;
    sum += rate;
  }
  return {
    points: rates.length,
    high,
    low,
    average: sum / rates.length,
    first,
    latest,
    change,
    changePct,
    direction: changePct > 0.01 ? "up" : changePct < -0.01 ? "down" : "flat",
    updated,
  };
}

export async function buildPairModel(baseInput: string, targetInput: string): Promise<PairModel> {
  const base = baseInput.toUpperCase();
  const target = targetInput.toUpperCase();
  const history = (await pairHistory(base, target)).filter((entry) => Number.isFinite(Number(entry.rate)));
  const latest = history.length ? history[history.length - 1] : null;
  const rates = history.map((entry) => Number(entry.rate));
  const rate = latest ? Number(latest.rate) : null;
  return {
    base,
    target,
    history,
    latest,
    rate,
    reverseRate: rate ? 1 / rate : null,
    stats: statsFor(rates, latest ? latest.ts : null),
    amounts: pairAmounts(base),
  };
}

/** Compact [[ts, rate], …] payload for the inline chart — the raw history is
 *  thousands of verbose objects for a chart a few hundred pixels wide. */
export function chartSeries(history: RateEntry[], maxPoints = PAIR_CHART_MAX_POINTS): [number, number][] {
  const points: Point[] = history.map((entry) => ({ ts: Math.trunc(entry.ts), value: Number(entry.rate) }));
  return downsamplePoints(points, maxPoints).map((point) => [point.ts, point.value]);
}

export type RangeOption = { key: string; label: string; seconds: number; enabled: boolean };

// 0 seconds means "everything stored". A window longer than the stored span
// would draw exactly the same line as the one before it, so those stay
// disabled instead of pretending to offer ten years of history.
const RANGE_WINDOWS: { key: string; label: string; seconds: number }[] = [
  { key: "12H", label: "12H", seconds: 12 * 3600 },
  { key: "1D", label: "1D", seconds: 24 * 3600 },
  { key: "1W", label: "1W", seconds: 7 * 24 * 3600 },
  { key: "1M", label: "1M", seconds: 30 * 24 * 3600 },
  { key: "1Y", label: "1Y", seconds: 365 * 24 * 3600 },
  { key: "2Y", label: "2Y", seconds: 2 * 365 * 24 * 3600 },
  { key: "5Y", label: "5Y", seconds: 5 * 365 * 24 * 3600 },
  { key: "10Y", label: "10Y", seconds: 10 * 365 * 24 * 3600 },
];

export function rangeOptions(series: [number, number][]): { options: RangeOption[]; defaultKey: string } {
  if (series.length < 2) {
    return {
      options: RANGE_WINDOWS.map((window) => ({ ...window, enabled: false })),
      defaultKey: RANGE_WINDOWS[RANGE_WINDOWS.length - 1].key,
    };
  }
  const span = series[series.length - 1][0] - series[0][0];
  const options: RangeOption[] = [];
  let defaultKey = "";
  for (const window of RANGE_WINDOWS) {
    // A window is worth offering while it still crops the stored history;
    // the first one that covers all of it becomes the default "whole
    // history" view, and anything wider is redundant.
    const enabled = !defaultKey;
    if (enabled && window.seconds >= span) defaultKey = window.key;
    options.push({ ...window, enabled: enabled && pointsInWindow(series, window.seconds) >= 2 });
  }
  if (!defaultKey) defaultKey = RANGE_WINDOWS[RANGE_WINDOWS.length - 1].key;
  const chosen = options.find((option) => option.key === defaultKey);
  if (chosen) chosen.enabled = true;
  return { options, defaultKey };
}

function pointsInWindow(series: [number, number][], seconds: number): number {
  const newest = series[series.length - 1][0];
  return series.filter(([ts]) => ts >= newest - seconds).length;
}

export type PairContent = {
  baseName: string;
  targetName: string;
  intent: string;
  summary: string;
  contextCards: { title: string; body: string }[];
  faqs: { question: string; answer: string }[];
  rangePct: number;
};

function trendPhrase(stats: PairStats | null): string {
  if (!stats) return "does not have enough stored history yet to describe a clear trend";
  if (stats.direction === "up") return "has moved higher across the stored data window";
  if (stats.direction === "down") return "has moved lower across the stored data window";
  return "has stayed inside a narrow range across the stored data window";
}

function rateScaleNote(rate: number | null, base: string, target: string): string {
  if (rate === null) return "As more update points are collected, this page will become more useful for comparing direction, range, and short-term changes.";
  if (Math.abs(rate) < 0.01) return `Because 1 ${base} is worth a small decimal amount of ${target}, the reverse rate and percentage change are often easier to read than the raw forward quote.`;
  if (Math.abs(rate) >= 1000) return `Because 1 ${base} converts into a large nominal amount of ${target}, small percentage moves can still appear as several units on the chart.`;
  return `The ${base}/${target} quote is readable on a normal scale, so the chart, high-low range, and average rate can be compared directly.`;
}

export function buildPairContent(model: PairModel): PairContent {
  const { base, target, stats, rate, reverseRate } = model;
  const baseProfile = currencyProfile(base);
  const targetProfile = currencyProfile(target);
  const latestLabel = rate === null ? "not available" : formatRate(rate);
  const reverseLabel = reverseRate === null ? "not available" : formatRate(reverseRate);
  const rangePct = stats && stats.average ? ((stats.high - stats.low) / stats.average) * 100 : 0;

  let intent: string;
  if (target === "VND") {
    intent = `This page is useful for reading how ${baseProfile.name} values translate into Vietnamese dong amounts for Vietnam travel, transfers, invoices, and local price comparison.`;
  } else if (base === "VND") {
    intent = `This page helps read Vietnamese dong values in ${targetProfile.name}, which is useful when local VND prices need to be compared with foreign budgets or savings.`;
  } else if (base === "USD") {
    intent = `Because USD is a ${baseProfile.role}, this pair is often used as a benchmark for checking how ${targetProfile.name} is moving against dollar-based pricing.`;
  } else if (target === "USD") {
    intent = `Quoting ${base} against USD makes the move easier to compare with global dollar strength, overseas costs, and USD-denominated references.`;
  } else {
    intent = `This cross-rate connects ${baseProfile.region} and ${targetProfile.region} without forcing the reader to manually convert through USD.`;
  }

  const summary = `${base}/${target} ${trendPhrase(stats)}. `
    + (stats
      ? `The observed range is about ${rangePct.toFixed(2)}% between the stored high and low, across ${stats.points} stored update points.`
      : "The stored sample is still building.");

  const contextCards = [
    {
      title: `Why ${base}/${target} matters`,
      body: `${base} is the ${baseProfile.name}, a ${baseProfile.role}. ${target} is the ${targetProfile.name}. ${intent}`,
    },
    {
      title: "How to read the quote",
      body: `The quote means 1 ${base} equals ${latestLabel} ${target}. A rising chart means ${base} buys more ${target}; a falling chart means it buys less. ${rateScaleNote(rate, base, target)}`,
    },
    {
      title: "Reverse-rate context",
      body: `The reverse view is 1 ${target} = ${reverseLabel} ${base}. This is especially useful when the forward pair is very large or very small, because the inverse quote may match how users mentally compare prices.`,
    },
    {
      title: "Practical use cases",
      body: `Readers commonly use this pair for ${baseProfile.use} against ${targetProfile.use}. The table gives practical amounts, while the chart and stats show whether the current quote is near the recent high, low, or average.`,
    },
  ];

  const strength = stats?.direction === "up" ? "stronger" : stats?.direction === "down" ? "weaker" : "mostly stable";
  const faqs = [
    {
      question: `What is the ${base} to ${target} exchange rate today?`,
      answer: rate === null ? "The latest stored rate is not available yet." : `The latest stored rate is 1 ${base} = ${latestLabel} ${target}.`,
    },
    {
      question: `Is ${base} stronger or weaker against ${target}?`,
      answer: stats
        ? `Across the current stored window, ${base} is ${strength} against ${target}, based on a ${stats.changePct.toFixed(2)}% move and a ${rangePct.toFixed(2)}% high-low range.`
        : "There is not enough stored history yet to describe the trend.",
    },
    { question: `When is the ${base}/${target} rate useful?`, answer: intent },
    {
      question: `Why compare ${target} to ${base} as the reverse rate?`,
      answer: `The reverse rate, currently 1 ${target} = ${reverseLabel} ${base}, can be easier to understand when the forward quote is a very large number or a very small decimal.`,
    },
    {
      question: "Can I use this rate for money transfers?",
      answer: "This page is for informational comparison only. Banks, brokers, card networks, and transfer providers may apply their own spreads, fees, settlement timing, and rounding.",
    },
  ];

  return { baseName: baseProfile.name, targetName: targetProfile.name, intent, summary, contextCards, faqs, rangePct };
}

export type ConversionRow = { from: string; to: string };

export function conversionRows(amounts: number[], base: string, target: string, rate: number | null): ConversionRow[] {
  return amounts.map((amount) => ({
    from: `${amount.toLocaleString("en-US")} ${base}`,
    to: rate === null ? "—" : `${formatAmount(amount * rate)} ${target}`,
  }));
}

export function pairPagePath(base: string, target: string): string {
  return pairUrl(base, target);
}
