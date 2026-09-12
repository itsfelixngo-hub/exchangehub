import type { APIRoute } from "astro";
import { buildHeroChart, buildHeroSecondary } from "../../lib/home";
import { configCurrencies } from "../../lib/config";

export const prerender = false;

export const GET: APIRoute = async ({ url }) => {
  const currencies = configCurrencies();
  const base = url.searchParams.get("base")?.toUpperCase();
  const target = url.searchParams.get("target")?.toUpperCase();
  if (!base || !target || base === target || !currencies.includes(base) || !currencies.includes(target)) {
    return new Response(JSON.stringify({ error: "unknown pair" }), {
      status: 400,
      headers: { "content-type": "application/json" },
    });
  }
  const chart = await buildHeroChart(base, target);
  if (!chart) {
    return new Response(JSON.stringify({ error: "no data" }), {
      status: 404,
      headers: { "content-type": "application/json" },
    });
  }
  const secondary = await buildHeroSecondary(base, target);
  return new Response(JSON.stringify({ ...chart, secondary }), {
    headers: { "content-type": "application/json" },
  });
};
