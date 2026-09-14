// @ts-check
import { defineConfig } from 'astro/config';

import node from '@astrojs/node';

// https://astro.build/config
export default defineConfig({
  output: 'server',
  adapter: node({
    mode: 'standalone'
  }),
  // One port for this project, everywhere: `astro dev`, `astro preview`, the
  // container, and the blue half of the blue/green pair on the VPS. Using the
  // production number locally means a link that works in one place works in
  // the other, and nothing has to be started on a second port to check it.
  // (`npm run smoke` is the exception — it boots its own throwaway server on
  // SMOKE_PORT so it can run while the dev server is up.)
  server: {
    port: 5003,
  },
  security: {
    // Astro's built-in check compares the Origin header against
    // `context.url.origin`, which behind nginx is the scheme of the *internal*
    // hop: `http://ratehubfx.com`. A browser on the real site sends
    // `Origin: https://ratehubfx.com`, so the two never matched and every
    // contact form submission came back 403.
    //
    // The check itself is worth keeping, so src/middleware.ts does the same
    // comparison against the forwarded origin instead of turning it off.
    checkOrigin: false,
  },
});
