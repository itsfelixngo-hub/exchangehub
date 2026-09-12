// @ts-check
import { defineConfig } from 'astro/config';

import node from '@astrojs/node';

// https://astro.build/config
export default defineConfig({
  output: 'server',
  adapter: node({
    mode: 'standalone'
  }),
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
