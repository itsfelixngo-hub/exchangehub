export function formatRate(value: number | string): string {
  const num = Number(value);
  const abs = Math.abs(num);
  if (num === 0) return "0";
  if (abs < 0.000001) return num.toExponential(6).toUpperCase().replace("E", "E");
  if (abs < 1) return trimTrailingZeros(num.toFixed(8));
  if (abs < 1000) return trimTrailingZeros(num.toFixed(6));
  return num.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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
