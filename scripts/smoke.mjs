// Boots the built server and checks the routes a deploy must not break.
// Run after `npm run build`:  node scripts/smoke.mjs
//
// It runs against fixture rate files rather than R2 or the live uploads
// directory, so CI needs no credentials and the assertions below can talk
// about known numbers instead of whatever the fetcher last wrote.
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const PORT = Number(process.env.SMOKE_PORT ?? "43210");
const BASE = `http://127.0.0.1:${PORT}`;
const SITE = "https://smoke.example";

const failures = [];
function check(name, ok, detail = "") {
  if (ok) {
    console.log(`  ok   ${name}`);
  } else {
    console.log(`  FAIL ${name}${detail ? ` — ${detail}` : ""}`);
    failures.push(name);
  }
}

// Two pairs against USD is enough for every code path: the stored-file route
// (usd_vnd), and the derived route that triangulates through the USD table
// (vnd_eur is never stored, it is computed from the two below).
function writeFixtures() {
  const dir = mkdtempSync(path.join(tmpdir(), "exchangehub-smoke-"));
  const rates = path.join(dir, "rates");
  mkdirSync(rates, { recursive: true });
  const now = Math.floor(Date.now() / 1000);
  const series = (base, target, from, to) =>
    Array.from({ length: 24 }, (_, i) => ({
      ts: now - (23 - i) * 3600,
      base,
      target,
      rate: from + ((to - from) * i) / 23,
    }));
  const files = {
    "vnd_usd.json": series("VND", "USD", 1 / 25000, 1 / 24500),
    "eur_usd.json": series("EUR", "USD", 1.05, 1.08),
    "jpy_usd.json": series("JPY", "USD", 1 / 150, 1 / 148),
  };
  for (const [name, rows] of Object.entries(files)) {
    writeFileSync(path.join(rates, name), JSON.stringify(rows));
  }
  writeFileSync(
    path.join(rates, "index.json"),
    JSON.stringify({ pairs: Object.keys(files).map((file) => ({ file })) }),
  );
  return dir;
}

async function waitForServer(deadlineMs = 30000) {
  const until = Date.now() + deadlineMs;
  while (Date.now() < until) {
    try {
      const res = await fetch(`${BASE}/healthz`);
      if (res.ok) return;
    } catch {
      // not listening yet
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`server did not answer on ${BASE} in time`);
}

const uploads = writeFixtures();
const server = spawn(process.execPath, ["./dist/server/entry.mjs"], {
  env: {
    ...process.env,
    HOST: "127.0.0.1",
    PORT: String(PORT),
    WP_UPLOADS: uploads,
    R2_ENABLED: "false",
    SITE_URL: SITE,
    CONTACT_SECRET: "smoke-only-secret",
  },
  stdio: ["ignore", "pipe", "inherit"],
});
server.stdout.resume();

try {
  await waitForServer();

  console.log("routes answer");
  for (const [route, expected] of [
    ["/", 200],
    ["/chart", 200],
    ["/contact", 200],
    ["/about", 200],
    ["/terms", 200],
    ["/privacy-policy", 200],
    ["/disclaimer", 200],
    ["/healthz", 200],
    ["/robots.txt", 200],
    ["/sitemap.xml", 200],
    ["/eur-usd", 200],
    ["/usd-vnd", 200],
    ["/vnd-eur", 200],
    ["/api/rates?quote=EUR", 200],
    ["/api/hero?base=USD&target=VND", 200],
    // Not two known currency codes, or both the same: a 404, not a page
    // about a pair we hold no rates for.
    ["/zz-yy", 404],
    ["/usd-usd", 404],
    ["/api/hero?base=USD&target=USD", 400],
  ]) {
    const res = await fetch(`${BASE}${route}`, { redirect: "manual" });
    check(`${route} -> ${expected}`, res.status === expected, `got ${res.status}`);
  }

  console.log("healthz identifies the build");
  const health = await (await fetch(`${BASE}/healthz`)).json();
  // `ok` and `service` are what the deploy scripts and the Flask-era tooling
  // read; the rest is what tells this stack apart from the one it replaced.
  check("healthz still reports ok", health.ok === true);
  check("healthz still reports the service", health.service === "exchangehub");
  check("healthz reports version 2", health.version === 2, String(health.version));
  check("healthz reports the astro stack", health.stack === "astro", health.stack);

  console.log("canonical URLs follow the proxy, not the socket");
  const home = await fetch(`${BASE}/`, { headers: { host: "ratehubfx.com" } });
  const html = await home.text();
  check("canonical is absolute https", html.includes(`<link rel="canonical" href="${SITE}/">`));
  check("og:url matches canonical", html.includes(`content="${SITE}/"`));
  const sitemap = await (await fetch(`${BASE}/sitemap.xml`)).text();
  check("sitemap uses the site origin", sitemap.includes(`<loc>${SITE}/</loc>`));
  check("sitemap lists pair pages", sitemap.includes(`<loc>${SITE}/usd-vnd</loc>`));
  const robots = await (await fetch(`${BASE}/robots.txt`)).text();
  check("robots points at the sitemap", robots.includes(`Sitemap: ${SITE}/sitemap.xml`));

  console.log("canonical redirects");
  for (const [from, to] of [
    ["/eur-usd/", "/eur-usd"],
    ["/EUR-USD", "/eur-usd"],
    ["/eur_usd", "/eur-usd"],
    ["/exchange/eur-usd", "/eur-usd"],
  ]) {
    const res = await fetch(`${BASE}${from}`, { redirect: "manual" });
    const location = res.headers.get("location") ?? "";
    check(`${from} -> ${to}`, res.status === 301 && location.endsWith(to), `got ${res.status} ${location}`);
  }

  console.log("cache policy");
  const htmlHeaders = (await fetch(`${BASE}/`)).headers;
  check(
    "HTML stays out of shared caches",
    (htmlHeaders.get("cache-control") ?? "").includes("private"),
    htmlHeaders.get("cache-control") ?? "(none)",
  );
  const apiHeaders = (await fetch(`${BASE}/api/rates?quote=USD`)).headers;
  check(
    "JSON is cacheable",
    (apiHeaders.get("cache-control") ?? "").includes("max-age=60"),
    apiHeaders.get("cache-control") ?? "(none)",
  );
  // An error answer must not be held at the edge for a minute.
  const errHeaders = (await fetch(`${BASE}/api/hero?base=USD&target=USD`)).headers;
  check(
    "JSON errors are not cacheable",
    !(errHeaders.get("cache-control") ?? "").includes("max-age=60"),
    errHeaders.get("cache-control") ?? "(none)",
  );

  console.log("rate data reaches the page");
  const pair = await (await fetch(`${BASE}/eur-usd`)).text();
  check("stored pair renders a rate", /1 EUR = 1\.0[0-9]+ USD/.test(pair));
  const derived = await (await fetch(`${BASE}/vnd-eur`)).text();
  check("derived pair renders a rate", /1 VND = 0\.0000[0-9]+ EUR/.test(derived));
  const api = await (await fetch(`${BASE}/api/rates?quote=USD`)).json();
  check("api returns rows", Array.isArray(api.rows) && api.rows.length > 0, `${api.rows?.length} rows`);
  check("api echoes the quote", api.quote === "USD", api.quote);

  console.log("contact form");
  const contact = await fetch(`${BASE}/contact`, { headers: { "x-forwarded-proto": "https" } });
  const cookie = contact.headers.get("set-cookie") ?? "";
  check("challenge cookie is HttpOnly", cookie.includes("HttpOnly"));
  check("challenge cookie is Secure behind TLS termination", cookie.includes("Secure"));
  // The regression this guards: Astro's built-in origin check compared the
  // browser's https Origin against the http scheme of the internal proxy hop,
  // so a real submission came back 403 and the form was unusable in
  // production. A same-site post must reach the handler and be answered with
  // validation errors, not forbidden.
  const sameSite = await fetch(`${BASE}/contact`, {
    method: "POST",
    headers: {
      host: "smoke.example",
      origin: SITE,
      "x-forwarded-proto": "https",
      "content-type": "application/x-www-form-urlencoded",
    },
    body: "name=a",
  });
  const sameSiteBody = await sameSite.text();
  check(
    "same-site submission behind TLS termination is not 403",
    sameSite.status === 200,
    `got ${sameSite.status}`,
  );
  check("empty submission is rejected with errors", sameSiteBody.includes("valid email"));

  // ...while a genuinely cross-site post is still refused.
  const crossSite = await fetch(`${BASE}/contact`, {
    method: "POST",
    headers: {
      host: "smoke.example",
      origin: "https://evil.example",
      "x-forwarded-proto": "https",
      "content-type": "application/x-www-form-urlencoded",
    },
    body: "name=a",
  });
  check("cross-site submission is forbidden", crossSite.status === 403, `got ${crossSite.status}`);
} finally {
  server.kill("SIGTERM");
  rmSync(uploads, { recursive: true, force: true });
}

if (failures.length) {
  console.error(`\n${failures.length} check(s) failed:\n  ${failures.join("\n  ")}`);
  process.exit(1);
}
console.log("\nall smoke checks passed");
