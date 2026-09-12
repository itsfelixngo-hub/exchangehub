// Visitor-geography helpers, keyed off the ISO-3166 country Cloudflare's
// edge already resolves per request (the CF-IPCountry header — present once
// the site is proxied through Cloudflare, no separate API token needed).
// Currency detection is the first consumer; the per-country table is the
// natural place to hang a future language/locale lookup (e.g. for
// Google-Translate-driven i18n) off the same country code, without a second
// header read or a second per-country table.
import { configCurrencies } from "./config";

export function getIpCountry(request: Request): string | null {
  const country = request.headers.get("cf-ipcountry")?.trim().toUpperCase();
  // Cloudflare sends "XX" for an unresolvable IP and "T1" for Tor exit nodes.
  if (!country || country === "XX" || country === "T1") return null;
  return country;
}

// Only covers countries whose currency is one we actually carry a rate for
// (CURRENCY_PROFILES in config.ts).
const CURRENCY_COUNTRIES: Record<string, string[]> = {
  USD: ["US"],
  EUR: ["DE", "FR", "IT", "ES", "NL", "BE", "AT", "PT", "IE", "FI", "GR", "LU", "SK", "SI", "EE", "LV", "LT", "CY", "MT", "HR"],
  JPY: ["JP"],
  GBP: ["GB"],
  CNY: ["CN"],
  VND: ["VN"],
  KRW: ["KR"],
  THB: ["TH"],
  SGD: ["SG"],
  AUD: ["AU"],
  CAD: ["CA"],
  CHF: ["CH", "LI"],
  HKD: ["HK"],
  INR: ["IN"],
  IDR: ["ID"],
  MYR: ["MY"],
  PHP: ["PH"],
  TWD: ["TW"],
  NZD: ["NZ"],
  AED: ["AE"],
  SAR: ["SA"],
  SEK: ["SE"],
  NOK: ["NO"],
  DKK: ["DK"],
  MXN: ["MX"],
  BRL: ["BR"],
  ZAR: ["ZA"],
};

const COUNTRY_TO_CURRENCY: Record<string, string> = Object.fromEntries(
  Object.entries(CURRENCY_COUNTRIES).flatMap(([currency, countries]) => countries.map((country) => [country, currency])),
);

export function currencyForCountry(countryCode?: string | null): string | null {
  if (!countryCode) return null;
  const currency = COUNTRY_TO_CURRENCY[countryCode.trim().toUpperCase()];
  return currency && configCurrencies().includes(currency) ? currency : null;
}

// The languages the Google Translate widget offers (see Header.astro).
// Only countries where that language is unambiguously the primary one are
// listed — better to default to English on a genuinely mixed-language
// country than guess wrong.
export const SUPPORTED_LANGUAGES = ["en", "vi", "zh-CN", "ja", "es", "fr"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

const LANGUAGE_COUNTRIES: Record<Exclude<SupportedLanguage, "en">, string[]> = {
  vi: ["VN"],
  "zh-CN": ["CN"],
  ja: ["JP"],
  es: ["ES", "MX", "AR", "CO", "PE", "CL", "VE", "EC", "GT", "CU", "BO", "DO", "HN", "PY", "SV", "NI", "CR", "PA", "UY"],
  fr: ["FR", "MC"],
};

// Object.fromEntries widens the value back to `string`, so the language type
// is restated here rather than lost.
const COUNTRY_TO_LANGUAGE = Object.fromEntries(
  Object.entries(LANGUAGE_COUNTRIES).flatMap(([lang, countries]) =>
    countries.map((country) => [country, lang] as [string, SupportedLanguage])),
) as Record<string, SupportedLanguage>;

export function languageForCountry(countryCode?: string | null): SupportedLanguage {
  if (!countryCode) return "en";
  return COUNTRY_TO_LANGUAGE[countryCode.trim().toUpperCase()] ?? "en";
}

// The reverse trip, for when a visitor picks a language by hand: it stands in
// for the country the IP header would otherwise supply, so the currency and
// the hero pair follow the chosen language. Deliberately routed back through
// currencyForCountry rather than a second language -> currency table, so the
// two directions can never drift apart.
const LANGUAGE_COUNTRY: Record<SupportedLanguage, string> = {
  en: "US",
  vi: "VN",
  "zh-CN": "CN",
  ja: "JP",
  es: "ES",
  fr: "FR",
};

export function isSupportedLanguage(lang?: string | null): lang is SupportedLanguage {
  return !!lang && (SUPPORTED_LANGUAGES as readonly string[]).includes(lang);
}

export function countryForLanguage(lang?: string | null): string | null {
  return isSupportedLanguage(lang) ? LANGUAGE_COUNTRY[lang] : null;
}

export type VisitorLocale = {
  /** Country the page's data follows: the picked language's country when the
   *  visitor chose one by hand, the IP country otherwise. */
  country: string | null;
  /** Language the header widget should translate into on load. */
  lang: SupportedLanguage;
  /** Currency that country prices in, falling back to USD. */
  currency: string;
};

// Every page that renders the header has to answer "which language is this
// visitor on" identically — a page that skips the cookie shows the English
// flag over Google-translated content, and drops the auto-translation the
// next page over still applies. One helper, so the answer cannot differ by
// page. The IP header decides the first render; a language picked by hand
// (stored in the site_lang cookie) outranks it from then on.
export function resolveVisitorLocale(request: Request, pickedLang?: string | null): VisitorLocale {
  const cfCountry = getIpCountry(request);
  const country = countryForLanguage(pickedLang) ?? cfCountry;
  return {
    country,
    lang: isSupportedLanguage(pickedLang) ? pickedLang : languageForCountry(cfCountry),
    currency: currencyForCountry(country) ?? "USD",
  };
}
