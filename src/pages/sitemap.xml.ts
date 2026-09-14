import type { APIRoute } from "astro";
import { siteOrigin } from "../lib/site";
import { XML_HEADERS, dataLastmod, renderIndex, sectionNames } from "../lib/sitemap";

export const prerender = false;

// The index. robots.txt points here, and Search Console follows it down to the
// sections — which is where the hierarchy lives, since the URLs themselves are
// deliberately flat. See src/lib/sitemap.ts.
//
// A section's lastmod is the newest date inside it. Every section holds at
// least one page built from rate data (the "pages" section has the home page),
// so that is the data date in all of them.
export const GET: APIRoute = async ({ request, url }) => {
  const origin = siteOrigin(request, url);
  const lastmod = await dataLastmod();
  return new Response(
    renderIndex(origin, sectionNames().map((name) => ({ name, lastmod }))),
    { headers: XML_HEADERS },
  );
};
