/**
 * One rate, written the way the whole site writes rates.
 *
 * The decimal count is capped — eight places under 1, six above it, two past a
 * thousand — but a cap alone is what makes a small number look broken: at eight
 * places 0.000000012 rounds to 0.00000001, and anything below that rounds to
 * 0.00000000, which trims to a flat "0". A rate that exists would be printed as
 * nothing at all, and a reader cannot tell that from an error.
 *
 * So the cap gives way to significant digits when it has to: enough places to
 * keep four of them, and a last check that what came out is not zero for a
 * value that is not. Nothing changes for ordinary rates — 0.86, 25,987.53 and
 * everything between take the same path they always did.
 */
export function formatRate(value: number | string): string {
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  const abs = Math.abs(num);
  if (num === 0) return "0";
  if (abs >= 1000) {
    return num.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  if (abs >= 1) return trimTrailingZeros(num.toFixed(6));
  // ceil(-log10(abs)) is the number of leading zeros after the point; three
  // more places carry four significant digits. toFixed accepts at most 100,
  // and 20 is already past any rate — below that the guard below takes over.
  const decimals = Math.min(20, Math.max(8, Math.ceil(-Math.log10(abs)) + 3));
  const text = trimTrailingZeros(num.toFixed(decimals));
  // Belt and braces: a value small enough to survive all of that would still
  // print as "0", so say it in the one notation that cannot round away.
  if (Number(text) === 0) return num.toExponential(4);
  return text;
}

export function formatAmount(value: number | string): string {
  const num = Number(value);
  if (Math.abs(num) >= 1000) {
    return num.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  return formatRate(num);
}

function trimTrailingZeros(text: string): string {
  if (!text.includes(".")) return text;
  return text.replace(/0+$/, "").replace(/\.$/, "");
}

const symbolCache = new Map<string, string>();

// Uses the runtime's own CLDR data instead of a hand-maintained map, so the
// converter can show "$1.00" / "€0.86" the way the design calls for without
// us tracking a symbol per currency by hand.
export function currencySymbol(code: string): string {
  const cached = symbolCache.get(code);
  if (cached !== undefined) return cached;
  let symbol = code;
  try {
    const part = new Intl.NumberFormat("en-US", { style: "currency", currency: code, currencyDisplay: "narrowSymbol" })
      .formatToParts(0)
      .find((p) => p.type === "currency");
    if (part) symbol = part.value;
  } catch {
    // unsupported currency code — fall back to the code itself
  }
  symbolCache.set(code, symbol);
  return symbol;
}
