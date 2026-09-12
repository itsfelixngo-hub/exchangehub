import type { APIRoute } from "astro";

export const prerender = false;

// Same shape the Flask app returned, plus the fields that say *which* build is
// answering: scripts/deploy_blue_green.sh polls this path (HEALTH_PATH) and
// the CI/deploy workflows assert on it, so `ok` and `service` keep their
// meaning and nothing that reads them has to change.
//
// It deliberately touches no rate data — a health check that loads the model
// would report the data source, not the process.
//
//   version  1 = the Flask app, 2 = this one. Baked into the image by its
//            Dockerfile (ARG APP_VERSION), NOT read from .env: both stacks
//            share one .env, so a value set there would report the same
//            number whichever container actually answered.
//   stack    the same answer in words, so a reader need not remember what 2 is.
//   build    the git short SHA, passed by scripts/deploy_astro.sh at image
//            build time — tells apart two deploys of the same version.
//   color    which half of the blue/green pair this container is.
//
// "unknown" rather than an omitted key when a value is missing, so the shape
// is the same however the container was started.
const BODY = JSON.stringify({
  ok: true,
  service: "exchangehub",
  version: Number(process.env.APP_VERSION) || 2,
  stack: "astro",
  build: process.env.APP_BUILD || "unknown",
  color: process.env.APP_COLOR || "unknown",
});

export const GET: APIRoute = () =>
  new Response(BODY, {
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
