import type { APIRoute } from "astro";
import { siteOrigin } from "../lib/site";

export const prerender = false;

// Carried over from the Flask app's /robots.txt: the same probe paths, which
// exist to stop crawlers wasting requests on the WordPress and admin URLs the
// old host attracted.
const DISALLOW = [
  "/.env",
  "/.git",
  "/wp-login.php",
  "/wp-admin",
  "/xmlrpc.php",
  "/wp-content",
  "/wp-includes",
  "/phpmyadmin",
  "/adminer",
  "/vendor",
];

export const GET: APIRoute = ({ request, url }) => {
  const origin = siteOrigin(request, url);
  const body = ["User-agent: *", "Allow: /", ...DISALLOW.map((path) => `Disallow: ${path}`), `Sitemap: ${origin}/sitemap.xml`, ""].join("\n");
  return new Response(body, { headers: { "content-type": "text/plain; charset=utf-8" } });
};
