import type { APIRoute } from "astro";
import { buildQuoteRateRows } from "../../lib/home";
import { configCurrencies } from "../../lib/config";

export const prerender = false;

export const GET: APIRoute = async ({ url }) => {
  const quoteParam = url.searchParams.get("quote")?.toUpperCase();
  const quote = quoteParam && configCurrencies().includes(quoteParam) ? quoteParam : "USD";
  const rows = await buildQuoteRateRows(quote);
  return new Response(JSON.stringify({ quote, rows }), {
    headers: { "content-type": "application/json" },
  });
};
