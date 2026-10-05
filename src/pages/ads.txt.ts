import type { APIRoute } from "astro";
import { ADSENSE_CLIENT } from "../lib/site";

export const prerender = false;

// AdSense checks /ads.txt for the publisher id. Built from the same
// ADSENSE_CLIENT as the ad script, so changing the secret updates both.
export const GET: APIRoute = () => {
  const body = ADSENSE_CLIENT
    ? `google.com, ${ADSENSE_CLIENT.replace(/^ca-/, "")}, DIRECT, f08c47fec0942fa0\n`
    : "";
  return new Response(body, { headers: { "content-type": "text/plain; charset=utf-8" } });
};
