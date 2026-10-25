// Checks a running site against what the AdSense resubmission depends on:
// one canonical host, canonical/robots tags, the sitemap, robots.txt, the
// trust pages, the contact address, and the 15 canonical pair pages.
//
//   npm run check:seo                              # http://localhost:5003 (astro dev)
//   npm run check:seo -- https://ratehubfx.com     # the live site
//
// Plain Node (>= 18, global fetch), no dependencies. Prints PASS / FAIL /
// SKIP / INFO per check and exits 1 on any FAIL. Against a local server the
// http -> https hop cannot be tested and is skipped; www is simulated with an
// X-Forwarded-Host header, which the app reads the same way it reads nginx's.

const BASE = (process.argv[2] ?? "http://localhost:5003").replace(/\/+$/, "");
const base = new URL(BASE);
const ORIGIN = base.origin;
const HOST = base.host;
const LOCAL = /^(localhost|127\.|0\.0\.0\.0|\[::1\])/.test(base.hostname);
const CONTACT_EMAIL = "contact@ratehubfx.com";
const TIMEOUT_MS = 30000;

// Mirrors CANONICAL_PAIRS in src/lib/config.ts. A plain list on purpose: this
// script checks the site from the outside, so it must not import the code it
// is checking.
const CANONICAL_PAIRS = [
  "eur-usd", "gbp-usd", "usd-jpy", "usd-cny",
  "usd-vnd", "eur-vnd", "gbp-vnd", "jpy-vnd", "cny-vnd",
  "eur-gbp", "eur-jpy", "eur-cny", "gbp-jpy", "gbp-cny", "cny-jpy",
];
const INFO_PAGES = ["/about", "/contact", "/privacy-policy", "/terms", "/disclaimer"];
const AMOUNTS = [1, 5, 10, 50, 100, 500, 1000];
const GOOGLEBOT_UA = "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 (KHTML, like Gecko) "
  + "Chrome/131.0.0.0 Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)";

let failures = 0;
function report(status, name, detail = "") {
  if (status === "FAIL") failures++;
  console.log(`  ${status.padEnd(4)} ${name}${detail ? `  — ${detail}` : ""}`);
}
const check = (name, ok, detail = "") => report(ok ? "PASS" : "FAIL", name, ok ? "" : detail);

async function get(url, init = {}) {
  return fetch(url, { redirect: "manual", signal: AbortSignal.timeout(TIMEOUT_MS), ...init });
}

const pageCache = new Map();
/** Body of a 200 page, fetched once; null (and a FAIL) when it does not answer 200. */
async function page(path) {
  if (pageCache.has(path)) return pageCache.get(path);
  let body = null;
  try {
    const res = await get(ORIGIN + path);
    if (res.status === 200) body = await res.text();
    else report("FAIL", `${path} answers 200`, `got ${res.status}${res.headers.get("location") ? ` -> ${res.headers.get("location")}` : ""}`);
  } catch (error) {
    report("FAIL", `${path} answers 200`, String(error?.message ?? error));
  }
  pageCache.set(path, body);
  return body;
}

const decode = (text) => text
  .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, " ");
const metaRobots = (html) => html.match(/<meta[^>]+name="robots"[^>]+content="([^"]*)"/i)?.[1] ?? "";
const canonicalOf = (html) => html.match(/<link[^>]+rel="canonical"[^>]+href="([^"]*)"/i)?.[1] ?? "";
const titleOf = (html) => decode(html.match(/<title>([^<]*)<\/title>/i)?.[1] ?? "").trim();
const descriptionOf = (html) => decode(html.match(/<meta[^>]+name="description"[^>]+content="([^"]*)"/i)?.[1] ?? "").trim();
const textOf = (fragment) => decode(fragment.replace(/<script[\s\S]*?<\/script>/gi, " ").replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();
/** The element with this id, up to its matching close tag (no nesting of the same tag inside). */
function byId(html, id) {
  const open = html.match(new RegExp(`<(\\w+)[^>]*\\bid="${id}"[^>]*>`));
  if (!open) return "";
  const start = open.index;
  const tag = open[1];
  let depth = 0;
  const re = new RegExp(`<(/?)${tag}\\b[^>]*>`, "gi");
  re.lastIndex = start;
  for (let m; (m = re.exec(html));) {
    depth += m[1] ? -1 : 1;
    if (depth === 0) return html.slice(start, m.index + m[0].length);
  }
  return html.slice(start);
}
const isNoindex = (robots) => /noindex/i.test(robots);

async function redirectCheck(label, url, headers = {}) {
  const expected = LOCAL ? null : `https://${HOST}/`;
  try {
    const res = await get(url, { headers });
    const location = res.headers.get("location") ?? "";
    if (LOCAL) {
      const target = location ? new URL(location, url) : null;
      check(`${label} -> one 301 to the non-www host`,
        res.status === 301 && target && !target.host.startsWith("www.") && target.pathname === "/",
        `got ${res.status} ${location || "(no location)"}`);
      return;
    }
    if (res.status !== 301 || location !== expected) {
      check(`${label} -> 301 ${expected}`, false, `got ${res.status} ${location || "(no location)"}`);
      return;
    }
    // One hop: the target itself must answer, not redirect again.
    const next = await get(location);
    check(`${label} -> 301 ${expected} in a single hop`, next.status === 200, `the target answered ${next.status}`);
  } catch (error) {
    check(`${label} redirects`, false, String(error?.message ?? error));
  }
}

console.log(`SEO check against ${ORIGIN}${LOCAL ? " (local: www simulated, http->https skipped)" : ""}\n`);

// 1. Redirects -------------------------------------------------------------
console.log("1. Canonical host");
if (LOCAL) {
  report("SKIP", "http -> https", "terminated by Cloudflare/nginx, not the app");
  await redirectCheck("www (X-Forwarded-Host)", `${ORIGIN}/`, { "x-forwarded-host": `www.${HOST}` });
} else {
  await redirectCheck(`http://${HOST}/`, `http://${HOST}/`);
  await redirectCheck(`https://www.${HOST}/`, `https://www.${HOST}/`);
  await redirectCheck(`http://www.${HOST}/`, `http://www.${HOST}/`);
}

// 2. Canonical and robots meta ---------------------------------------------
console.log("\n2. Canonical and robots");
for (const [path, wantCanonical, wantNoindex] of [
  ["/usd-vnd", "/usd-vnd", false],
  ["/vnd-usd", "/usd-vnd", false],
  ["/brl-dkk", "/brl-dkk", true],
]) {
  const html = await page(path);
  if (!html) continue;
  const robots = metaRobots(html);
  check(`${path} canonical = ${wantCanonical}`, canonicalOf(html) === ORIGIN + wantCanonical, canonicalOf(html) || "(none)");
  if (wantNoindex) check(`${path} is noindex,follow`, robots.replace(/\s/g, "") === "noindex,follow", robots || "(no robots meta)");
  else check(`${path} has no noindex`, !isNoindex(robots), robots);
}

// 3. sitemap.xml -------------------------------------------------------------
console.log("\n3. sitemap.xml");
const sitemapRes = await get(`${ORIGIN}/sitemap.xml`).catch(() => null);
const sitemap = sitemapRes?.status === 200 ? await sitemapRes.text() : "";
check("sitemap.xml answers 200", Boolean(sitemap), `got ${sitemapRes?.status ?? "no answer"}`);
const locs = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => decode(m[1]).trim());
const expectedLocs = ["/", ...INFO_PAGES, ...CANONICAL_PAIRS.map((pair) => `/${pair}`)].map((path) => ORIGIN + path);
check(`exactly ${expectedLocs.length} URLs`, locs.length === expectedLocs.length, `found ${locs.length}`);
const missing = expectedLocs.filter((loc) => !locs.includes(loc));
const extra = locs.filter((loc) => !expectedLocs.includes(loc));
check("home + 5 info pages + 15 canonical pairs, nothing else", !missing.length && !extra.length,
  [missing.length && `missing ${missing.join(", ")}`, extra.length && `unexpected ${extra.join(", ")}`].filter(Boolean).join("; "));
check("every URL is on the canonical host", locs.every((loc) => new URL(loc).origin === ORIGIN),
  locs.filter((loc) => new URL(loc).origin !== ORIGIN).join(", "));
const sitemapProblems = [];
for (const loc of locs) {
  const path = new URL(loc).pathname;
  const html = await page(path);
  if (html === null) { sitemapProblems.push(`${path} not 200`); continue; }
  if (isNoindex(metaRobots(html))) sitemapProblems.push(`${path} is noindex`);
}
check("every URL answers 200 and none is noindex", !sitemapProblems.length, sitemapProblems.join("; "));

// 4. robots.txt --------------------------------------------------------------
console.log("\n4. robots.txt");
const robotsRes = await get(`${ORIGIN}/robots.txt`).catch(() => null);
const robotsTxt = robotsRes?.status === 200 ? await robotsRes.text() : "";
check("robots.txt answers 200", Boolean(robotsTxt), `got ${robotsRes?.status ?? "no answer"}`);
// Groups of user-agent lines followed by rules; a bot obeys its own group if
// it has one, otherwise `*`. AdsBot ignores `*` entirely, so only a group
// naming it can block it.
const groups = [];
let current = null;
for (const raw of robotsTxt.split(/\r?\n/)) {
  const line = raw.replace(/#.*/, "").trim();
  const m = line.match(/^([A-Za-z-]+)\s*:\s*(.*)$/);
  if (!m) continue;
  const key = m[1].toLowerCase();
  if (key === "user-agent") {
    if (!current || current.rules.length) groups.push((current = { agents: [], rules: [] }));
    current.agents.push(m[2].toLowerCase());
  } else if ((key === "allow" || key === "disallow") && current) {
    current.rules.push({ allow: key === "allow", path: m[2] });
  }
}
function blocked(agent, path) {
  const own = groups.filter((g) => g.agents.some((a) => a !== "*" && agent.startsWith(a)));
  const applicable = own.length ? own : agent === "adsbot-google" ? [] : groups.filter((g) => g.agents.includes("*"));
  let best = null;
  for (const rule of applicable.flatMap((g) => g.rules)) {
    if (!rule.path || !path.startsWith(rule.path.replace(/\*.*$/, ""))) continue;
    if (!best || rule.path.length > best.path.length || (rule.path.length === best.path.length && rule.allow)) best = rule;
  }
  return Boolean(best && !best.allow);
}
for (const agent of ["googlebot", "mediapartners-google", "adsbot-google"]) {
  const hits = ["/", "/usd-vnd", "/brl-dkk", "/about", "/sitemap.xml"].filter((path) => blocked(agent, path));
  check(`${agent} may crawl the site`, !hits.length, `blocked: ${hits.join(", ")}`);
}
check("references the sitemap", new RegExp(`^Sitemap:\\s*${ORIGIN.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}/sitemap\\.xml\\s*$`, "mi").test(robotsTxt),
  (robotsTxt.match(/^Sitemap:.*$/mi) ?? ["(no Sitemap line)"])[0]);

// 5. Trust pages ------------------------------------------------------------
console.log("\n5. Trust pages");
for (const path of INFO_PAGES) {
  const html = await page(path);
  if (html) check(`${path} answers 200`, true);
}
const home = await page("/");
if (home) {
  const footer = home.match(/<footer\b[\s\S]*?<\/footer>/i)?.[0] ?? "";
  const header = home.match(/<header\b[\s\S]*?<\/header>/i)?.[0] ?? "";
  check("footer is present", Boolean(footer), "no <footer> element on /");
  const unlinked = INFO_PAGES.filter((path) => !footer.includes(`href="${path}"`));
  check("footer links all five trust pages", !unlinked.length, `missing ${unlinked.join(", ")}`);
  const headerMissing = ["/about", "/contact"].filter((path) => !header.includes(`href="${path}"`));
  check("header links About and Contact", !headerMissing.length, `missing ${headerMissing.join(", ")}`);
}

// 6. Email ------------------------------------------------------------------
console.log("\n6. Email addresses");
const contact = await page("/contact");
if (contact) check(`/contact shows ${CONTACT_EMAIL}`, contact.includes(CONTACT_EMAIL));
// Every page fetched so far plus a few that are not in the sitemap.
for (const path of ["/analysis", "/chart", "/usd", "/vnd-usd", "/brl-dkk"]) await page(path);
const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}/g;
const ASSET = /\.(png|jpe?g|gif|svg|webp|avif|ico|css|js|mjs|woff2?)$/i;
const strays = new Map();
for (const [path, html] of pageCache) {
  if (!html) continue;
  if (/gmail\.com/i.test(html)) strays.set(`${path}: gmail.com`, true);
  for (const [address] of html.matchAll(EMAIL)) {
    if (ASSET.test(address) || address.toLowerCase() === CONTACT_EMAIL) continue;
    strays.set(`${path}: ${address}`, true);
  }
}
check(`no address other than ${CONTACT_EMAIL} on ${[...pageCache.values()].filter(Boolean).length} pages`, !strays.size, [...strays.keys()].slice(0, 8).join("; "));

// 7. Canonical pair pages -----------------------------------------------------
console.log("\n7. The 15 canonical pair pages");
const normalise = (text) => text
  .replace(/\b[A-Z]{3}\b/g, "<CUR>")
  .replace(/[+−-]?\d[\d,.]*(?:e[+-]?\d+)?%?/gi, "<N>")
  .replace(/\s+/g, " ")
  .trim();
const pairs = [];
for (const pair of CANONICAL_PAIRS) {
  const path = `/${pair}`;
  const html = await page(path);
  if (!html) continue;
  const problems = [];
  const forward = html.match(/data-table-body="forward"[\s\S]*?<\/table>/)?.[0] ?? "";
  const amounts = [...forward.matchAll(/data-amount="(\d+)"/g)].map((m) => Number(m[1]));
  if (amounts.join(",") !== AMOUNTS.join(",")) problems.push(`conversion rows ${amounts.join(",") || "(none)"}`);
  const text = textOf(html.slice(html.indexOf("<body")));
  if (!/\b7[ -]days?\b/i.test(text)) problems.push('no "7 days"');
  if (/\b30[ -]days?\b/i.test(text)) problems.push('says "30 days"');
  if (!/Last updated <time datetime="[^"]+"/.test(html)) problems.push("no last-updated <time>");
  if (!text.includes("Open Exchange Rates")) problems.push("no data source");
  const summary = textOf(byId(html, "pair-summary"));
  const faq = textOf(byId(html, "faq"));
  if (summary.length < 40) problems.push("no summary");
  const faqCount = (byId(html, "faq").match(/class="faq-q"/g) ?? []).length;
  if (faqCount < 3 || faqCount > 4) problems.push(`${faqCount} FAQs`);
  check(`${path}`, !problems.length, problems.join("; "));
  pairs.push({ path, title: titleOf(html), description: descriptionOf(html), summary: normalise(summary), faq: normalise(faq) });
}
function duplicates(field) {
  const seen = new Map();
  const dupes = [];
  for (const item of pairs) {
    const key = item[field];
    if (seen.has(key)) dupes.push(`${seen.get(key)} = ${item.path}`);
    else seen.set(key, item.path);
  }
  return dupes;
}
if (pairs.length) {
  for (const [field, label] of [
    ["title", "unique <title>"],
    ["description", "unique meta description"],
    ["summary", "summary differs once codes and numbers are masked"],
    ["faq", "FAQ differs once codes and numbers are masked"],
  ]) {
    const dupes = duplicates(field);
    check(`${label} across ${pairs.length} pages`, !dupes.length, dupes.join("; "));
  }
}

// 8. Googlebot hint -----------------------------------------------------------
console.log("\n8. Googlebot user agent (hint only)");
try {
  const res = await get(`${ORIGIN}/usd-vnd`, { headers: { "user-agent": GOOGLEBOT_UA } });
  const challenged = res.status === 403 || res.status === 503 || /cf-mitigated|challenge/i.test(res.headers.get("cf-mitigated") ?? "");
  report("INFO", `/usd-vnd as Googlebot -> ${res.status}`,
    challenged
      ? "blocked or challenged — expected if Cloudflare checks that 'Googlebot' really comes from Google's IPs. Confirm with URL Inspection in Search Console."
      : "answered normally. The real test is URL Inspection in Search Console.");
} catch (error) {
  report("INFO", "/usd-vnd as Googlebot", String(error?.message ?? error));
}

console.log(`\n${failures ? `${failures} check(s) failed` : "All checks passed"}`);
process.exit(failures ? 1 : 0);
