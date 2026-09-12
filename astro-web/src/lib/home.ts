import {
  MAJOR_COLUMNS, HOME_ROWS, HOME_CHART_BASES, CONVERTER_TARGETS,
  MENU_GROUPS, configCurrencies, pairUrl,
} from "./config";
import { buildLatestUsdTable, deriveRateFromUsdTable, mapLimited, memoByTtl, pairHistory } from "./rates";
import { formatRate } from "./format";

const CHART_MAX_POINTS = Number(process.env.CHART_MAX_POINTS ?? "400");

export type Point = { ts: number; value: number };

export function downsamplePoints(points: Point[], maxPoints = CHART_MAX_POINTS): Point[] {
  if (points.length <= maxPoints || maxPoints < 2) return points;
  const span = Math.trunc(points[points.length - 1].ts) - Math.trunc(points[0].ts);
  if (span <= 0) return points.slice(-maxPoints);
  const bucket = Math.max(1, Math.floor(span / (maxPoints - 1)));
  const kept: Point[] = [];
  let lastBucket: number | null = null;
  for (const point of points) {
    const current = Math.floor(Math.trunc(point.ts) / bucket);
    if (current !== lastBucket) {
      kept.push(point);
      lastBucket = current;
    }
  }
  if (kept[kept.length - 1] !== points[points.length - 1]) kept.push(points[points.length - 1]);
  return kept;
}

export async function normalizedHistory(base: string, quote: string): Promise<Point[]> {
  const history = await pairHistory(base, quote);
  const points: Point[] = [];
  let first: number | null = null;
  for (const entry of history) {
    const rate = Number(entry.rate);
    if (first === null) first = rate;
    if (first) points.push({ ts: entry.ts, value: (rate / first) * 100 });
  }
  return downsamplePoints(points);
}

export type MatrixRow = { base: string; cells: { target: string; value: string | null; href: string }[] };

export async function buildHomeMatrix(): Promise<{ rows: MatrixRow[]; latestTs: number | null }> {
  const { table, latestTs } = await buildLatestUsdTable();
  const rows: MatrixRow[] = HOME_ROWS.map((base) => ({
    base,
    cells: MAJOR_COLUMNS.map((target) => {
      const rate = deriveRateFromUsdTable(base, target, table);
      return { target, value: rate === null ? null : formatRate(rate), href: pairUrl(base, target) };
    }),
  }));
  return { rows, latestTs };
}

export type Mover = {
  label: string;
  href: string;
  rate: string;
  changePct: number;
  changeLabel: string;
  direction: "up" | "down" | "flat";
};

export type PairMovers = { up: Mover[]; down: Mover[]; flat: Mover[] };

// Around forty pair histories, rebuilt from scratch on every page render even
// though the rate data behind them only changes once a refresh window. Memoed
// on that same window, keyed by the base filter ("" meaning every group).
const moversFor = memoByTtl(computeMovers);

async function computeMovers(baseFilter: string): Promise<Mover[]> {
  const seen = new Set<string>();
  const wanted: [string, string][] = [];
  for (const [base, targets] of Object.entries(MENU_GROUPS)) {
    if (baseFilter && base !== baseFilter) continue;
    for (const target of targets) {
      const seenKey = `${base}/${target}`;
      if (base === target || seen.has(seenKey)) continue;
      seen.add(seenKey);
      wanted.push([base, target]);
    }
  }

  // Each pairHistory is potentially one R2 round trip. Awaiting them one at a
  // time made a cold render pay the sum of every latency instead of a few
  // batches of it; mapLimited caps how many are in flight at once.
  const built = await mapLimited(wanted, async ([base, target]): Promise<Mover | null> => {
    const history = await pairHistory(base, target);
    const rates = history.map((e) => Number(e.rate)).filter((r) => Number.isFinite(r));
    if (!rates.length) return null;
    const first = rates[0];
    const latest = rates[rates.length - 1];
    const changePct = first ? ((latest - first) / first) * 100 : 0;
    return {
      label: `${base}/${target}`,
      href: pairUrl(base, target),
      rate: formatRate(latest),
      changePct,
      changeLabel: `${changePct >= 0 ? "+" : ""}${changePct.toFixed(4)}%`,
      direction: changePct > 0.01 ? "up" : changePct < -0.01 ? "down" : "flat",
    };
  });
  return built.filter((mover): mover is Mover => mover !== null);
}

export async function buildPairMovers(limit = 6, baseFilter?: string): Promise<PairMovers> {
  // Splitting and sorting a few dozen already-built movers is cheap, so only
  // the histories behind them are memoed — `limit` and the sort stay per call.
  const movers = await moversFor(baseFilter ? baseFilter.toUpperCase() : "");
  const up = movers.filter((m) => m.direction === "up").sort((a, b) => b.changePct - a.changePct).slice(0, limit);
  const down = movers.filter((m) => m.direction === "down").sort((a, b) => a.changePct - b.changePct).slice(0, limit);
  const flat = movers.filter((m) => m.direction === "flat").sort((a, b) => Math.abs(a.changePct) - Math.abs(b.changePct)).slice(0, limit);
  return { up, down, flat };
}

// Derived pairs (anything not stored as its own file) are triangulated
// through a merged multi-currency timeline. A currency that ticks less
// often than the timeline itself repeats its last known value across many
// consecutive timeline entries, so a naive "last N points" tail is often
// flat even though the pair genuinely moves over time. Walk backwards and
// keep only value changes so the sparkline reflects real movement.
export function distinctTail(values: number[], count: number): number[] {
  const kept: number[] = [];
  for (let i = values.length - 1; i >= 0 && kept.length < count; i--) {
    if (kept.length === 0 || kept[kept.length - 1] !== values[i]) {
      kept.push(values[i]);
    }
  }
  return kept.reverse();
}

export function sparkSvgPoints(values: number[], width = 400, height = 88, pad = 6): string {
  if (values.length < 2) return "";
  // Looped rather than spread for the same reason as statsFor: the hero card
  // falls back to the whole stored history when its 24H window is too thin.
  let lo = values[0];
  let hi = values[0];
  for (const value of values) {
    if (value < lo) lo = value;
    if (value > hi) hi = value;
  }
  const span = hi - lo || 1;
  const step = width / (values.length - 1);
  return values
    .map((value, i) => {
      const x = i * step;
      const y = pad + (1 - (value - lo) / span) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export const HERO_WINDOW_HOURS = 24;

export type HeroChart = {
  label: string;
  rate: string;
  changeLabel: string;
  direction: "up" | "down" | "flat";
  points: string;
  /** Vertical position of the last point, in % of the chart height, so the
   *  live dot can be placed on the end of the line from outside the SVG
   *  (which is drawn with preserveAspectRatio="none" and would squash a
   *  circle into an ellipse). */
  dotY: number;
};

export type HeroTile = { label: string; rate: string; href: string };
export type HeroHighlight = HeroChart & { secondary: HeroTile[] };

// The tiles under the chart quote the same base currency as the chart above
// them — showing unrelated top movers there reads as if they belonged to the
// pair on display. Priced off the latest USD table rather than per-pair
// history, since a tile only shows a rate.
export async function buildHeroSecondary(base: string, exclude: string, limit = 3): Promise<HeroTile[]> {
  const { table } = await buildLatestUsdTable();
  const tiles: HeroTile[] = [];
  for (const target of MAJOR_COLUMNS) {
    if (tiles.length >= limit) break;
    if (target === base || target === exclude) continue;
    const rate = deriveRateFromUsdTable(base, target, table);
    if (rate === null) continue;
    tiles.push({ label: `${base}/${target}`, rate: formatRate(rate), href: pairUrl(base, target) });
  }
  return tiles;
}

// The card is labelled 24H, so both the line and the change figure have to
// cover exactly that window — the stored history runs about a week, and
// reporting a week's movement under a 24H badge would be plain wrong. Falls
// back to the whole history only when the window holds too little to plot.
export async function buildHeroChart(base: string, target: string): Promise<HeroChart | null> {
  const history = (await pairHistory(base, target)).filter((e) => Number.isFinite(Number(e.rate)));
  if (!history.length) return null;

  const newestTs = history[history.length - 1].ts;
  const windowed = history.filter((e) => e.ts >= newestTs - HERO_WINDOW_HOURS * 3600);
  const values = (windowed.length >= 2 ? windowed : history).map((e) => Number(e.rate));

  const first = values[0];
  const latest = values[values.length - 1];
  const changePct = first ? ((latest - first) / first) * 100 : 0;
  const points = sparkSvgPoints(values);
  const lastY = Number(points.split(" ").pop()?.split(",")[1] ?? 0);

  return {
    label: `${base}/${target}`,
    rate: formatRate(latest),
    changeLabel: `${changePct >= 0 ? "+" : ""}${changePct.toFixed(4)}%`,
    direction: changePct > 0.01 ? "up" : changePct < -0.01 ? "down" : "flat",
    points,
    dotY: (lastY / 88) * 100,
  };
}

export async function buildHeroHighlight(movers: PairMovers, primaryPair?: [string, string]): Promise<HeroHighlight | null> {
  const candidates = [...movers.up, ...movers.down, ...movers.flat];
  const fallback = candidates[0] ? (candidates[0].label.split("/") as [string, string]) : null;
  const pair = primaryPair ?? fallback;
  if (!pair) return null;

  const chart = (await buildHeroChart(pair[0], pair[1]))
    ?? (fallback ? await buildHeroChart(fallback[0], fallback[1]) : null);
  if (!chart) return null;

  const [chartBase, chartTarget] = chart.label.split("/");
  return { ...chart, secondary: await buildHeroSecondary(chartBase, chartTarget) };
}

export type RateRow = {
  target: string;
  rate: string;
  changeLabel: string;
  direction: "up" | "down" | "flat";
  points: string;
  href: string;
};

// Every configured currency is triangulated through the USD table (see
// deriveRateFromUsdTable), so the full rate board isn't limited to the
// hand-picked MENU_GROUPS pairs the way buildPairMovers is — a quote like
// KRW or THB has no MENU_GROUPS entry of its own and would otherwise show
// zero rows here.
export async function buildQuoteRateRows(quote: string, limit?: number): Promise<RateRow[]> {
  const rows = await quoteRateRowsFor(quote.toUpperCase());
  return limit ? rows.slice(0, limit) : rows;
}

// Memoed like the movers above: /api/rates?quote= is fetched again on every
// language or currency switch, and the answer only changes when the rate data
// behind it does.
const quoteRateRowsFor = memoByTtl(computeQuoteRateRows);

async function computeQuoteRateRows(base: string): Promise<RateRow[]> {
  const targets = configCurrencies().filter((c) => c !== base);
  // Same reason as buildPairMovers: one round trip per target, fetched in
  // bounded batches rather than in sequence. mapLimited keeps the input order,
  // so the board still lists currencies in configCurrencies() order.
  const built = await mapLimited(targets, async (target): Promise<RateRow | null> => {
    const history = await pairHistory(base, target);
    const values = history.map((e) => Number(e.rate)).filter((r) => Number.isFinite(r));
    if (!values.length) return null;
    const first = values[0];
    const latest = values[values.length - 1];
    const changePct = first ? ((latest - first) / first) * 100 : 0;
    return {
      target,
      rate: formatRate(latest),
      changeLabel: `${changePct >= 0 ? "+" : ""}${changePct.toFixed(4)}%`,
      direction: changePct > 0.01 ? "up" : changePct < -0.01 ? "down" : "flat",
      points: sparkSvgPoints(distinctTail(values, 20), 120, 30, 3),
      href: pairUrl(base, target),
    };
  });
  return built.filter((row): row is RateRow => row !== null);
}

export function chartDescriptionForQuote(quote: string): string {
  return `<p>This chart compares major currencies against <strong>${quote}</strong> using a base-100 index. `
    + `Every line starts at <strong>100</strong> at the first available point, so the chart measures relative percentage movement instead of raw exchange-rate size.</p>`
    + `<p>Example: if <strong>EUR to ${quote}</strong> moves from 100 to 102, EUR has strengthened by about 2% against ${quote}. `
    + `If <strong>VND to ${quote}</strong> moves from 100 to 98, VND has weakened by about 2% against ${quote}. `
    + `A line staying close to 100 means the currency has been mostly flat versus ${quote} in the selected data window.</p>`
    + `<p>This normalization is useful because raw rates use very different scales, for example 1 USD can equal tens of thousands of VND but less than 1 EUR. `
    + `Indexing every line to 100 lets you compare which currency is moving faster or slower on the same chart.</p>`;
}

function utcIso(ts: number): string {
  return new Date(ts * 1000).toISOString().replace(/\.\d{3}Z$/, "Z");
}

export type HomeModel = {
  columns: string[];
  quote: string;
  quoteOptions: string[];
  chartBases: string[];
  converterBases: string[];
  converterTargets: string[];
  latestUsdTable: Record<string, number>;
  rows: MatrixRow[];
  pairMovers: PairMovers;
  series: { label: string; data: Point[] }[];
  chartDescription: string;
  updated: string;
  updatedIso: string;
  hero: HeroHighlight | null;
};

export async function buildHomeModel(quoteInput = "USD", includeSeries = true, heroPair?: [string, string]): Promise<HomeModel> {
  let quote = quoteInput.toUpperCase();
  if (!configCurrencies().includes(quote)) quote = "USD";
  // Four independent reads of the same cached rate set. Started together so a
  // cold render waits once for the data layer instead of four times over.
  const [{ rows, latestTs }, { table: latestUsdTable }, pairMovers, series] = await Promise.all([
    buildHomeMatrix(),
    buildLatestUsdTable(),
    buildPairMovers(),
    includeSeries
      ? Promise.all(
          HOME_CHART_BASES.filter((base) => base !== quote).map(async (base) => ({
            label: `${base} to ${quote}`,
            data: await normalizedHistory(base, quote),
          })),
        )
      : Promise.resolve([] as { label: string; data: Point[] }[]),
  ]);
  return {
    columns: MAJOR_COLUMNS,
    quote,
    quoteOptions: MAJOR_COLUMNS,
    chartBases: HOME_CHART_BASES,
    converterBases: MAJOR_COLUMNS,
    converterTargets: CONVERTER_TARGETS,
    latestUsdTable,
    rows,
    pairMovers,
    series,
    chartDescription: chartDescriptionForQuote(quote),
    updated: latestTs ? new Date(latestTs * 1000).toISOString().slice(0, 16).replace("T", " ") + " UTC" : "",
    updatedIso: latestTs ? utcIso(latestTs) : "",
    hero: await buildHeroHighlight(pairMovers, heroPair),
  };
}
