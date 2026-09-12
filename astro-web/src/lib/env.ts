// Astro/Vite loads .env into import.meta.env, but our data layer reads plain
// process.env (shared code style with the old Python backend it replaces).
// Importing this first guarantees process.env is populated the same way in
// `astro dev`, `astro build`, and the standalone Node server in production.
//
// The app shares the repo-root .env with the Flask app it replaces: R2
// credentials, contact SMTP and the rest are configured once, in one file.
// Files are loaded from the working directory upwards to the repo root, and
// dotenv keeps the first value it sees for a key — so astro-web/.env can
// override a single value for local work without holding a second copy of
// every secret. Walking up (rather than a fixed "../.env") also means it
// finds the file whether the process starts in astro-web/ or at the repo
// root, which `astro dev` and the built server respectively do.
import fs from "node:fs";
import path from "node:path";
import dotenv from "dotenv";

const MAX_LEVELS = 6;

let dir = path.resolve(process.cwd());
for (let level = 0; level < MAX_LEVELS; level++) {
  const candidate = path.join(dir, ".env");
  if (fs.existsSync(candidate)) {
    dotenv.config({ path: candidate, override: false, quiet: true });
  }
  // The repo root is the last place worth reading; above it lies the home
  // directory, whose .env has nothing to do with this app.
  if (fs.existsSync(path.join(dir, ".git"))) break;
  const parent = path.dirname(dir);
  if (parent === dir) break;
  dir = parent;
}
