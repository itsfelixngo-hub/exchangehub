// Fails the build if sitemap.xml would list anything but the home page, the
// info pages and the 15 core pairs in their canonical direction — a non-core
// pair, a reverse direction, a duplicate. Runs before `astro build`:
//   node scripts/check-sitemap.mjs
//
// The sitemap is rendered per request, so there is no built file to inspect.
// Instead this loads the same src/lib/sitemap.ts the route uses, through
// Vite (which Astro already ships) so the TypeScript and the JSON import
// resolve exactly as they do in the app. Importing src/lib/config.ts also runs
// its own check that CANONICAL_PAIRS covers INDEXABLE_CURRENCIES.
import { createServer } from "vite";

const vite = await createServer({
  configFile: false,
  logLevel: "error",
  server: { middlewareMode: true, hmr: false, watch: null },
  appType: "custom",
  optimizeDeps: { noDiscovery: true, include: [] },
});

let failed = false;
try {
  const { CANONICAL_PAIRS, sitemapEntries, sitemapProblems } = await loadModules();
  const entries = sitemapEntries("2000-01-01");
  const problems = sitemapProblems(entries);
  const pairCount = entries.filter(({ path }) => /^\/[a-z]{3}-[a-z]{3}$/.test(path)).length;
  if (pairCount !== CANONICAL_PAIRS.length) {
    problems.push(`expected ${CANONICAL_PAIRS.length} pairs in the sitemap, found ${pairCount}`);
  }
  if (problems.length) {
    failed = true;
    console.error("sitemap check failed:");
    for (const problem of problems) console.error(`  - ${problem}`);
  } else {
    console.log(`sitemap check: ${entries.length} URLs, ${pairCount} core pairs, nothing else`);
  }
} catch (error) {
  failed = true;
  console.error("sitemap check failed:", error instanceof Error ? error.message : error);
} finally {
  await vite.close();
}

async function loadModules() {
  const sitemap = await vite.ssrLoadModule("/src/lib/sitemap.ts");
  const config = await vite.ssrLoadModule("/src/lib/config.ts");
  return { ...sitemap, CANONICAL_PAIRS: config.CANONICAL_PAIRS };
}

process.exit(failed ? 1 : 0);
