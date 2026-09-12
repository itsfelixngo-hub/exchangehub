// Round flag icons from circle-flags (HatScripts, MIT — see
// public/flags/LICENSE.md), served from /flags as plain <img> sources.
// They are drawn as circles rather than rectangles cropped into one, so
// nothing that identifies a flag is lost (the US canton, China's stars and
// Malaysia's canton all sit where a circular crop would cut them off).
const CURRENCY_FLAG_FILE: Record<string, string> = {
  USD: "us",
  EUR: "eu",
  JPY: "jp",
  GBP: "gb",
  CNY: "cn",
  VND: "vn",
  KRW: "kr",
  THB: "th",
  SGD: "sg",
  AUD: "au",
  CAD: "ca",
  CHF: "ch",
  HKD: "hk",
  INR: "in",
  IDR: "id",
  MYR: "my",
  PHP: "ph",
  TWD: "tw",
  NZD: "nz",
  AED: "ae",
  SAR: "sa",
  SEK: "se",
  NOK: "no",
  DKK: "dk",
  MXN: "mx",
  BRL: "br",
  ZAR: "za",
};

export function flagSrc(code: string): string | null {
  const file = CURRENCY_FLAG_FILE[code.toUpperCase()];
  return file ? `/flags/${file}.svg` : null;
}

export const SWAP_ICON = `<path d="M7 7h11l-3-3M17 17H6l3 3"/>`;
export const CHEVRON_DOWN = `<path d="M6 9l6 6 6-6"/>`;
export const ARROW_UP = `<path d="M12 19V5M6 11l6-6 6 6"/>`;
