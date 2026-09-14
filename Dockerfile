# Two stages so the runtime image carries no build toolchain and no dev
# dependencies: the Astro CLI, vite and the TypeScript types are needed to
# produce dist/ and are worthless afterwards.
#
# Node 22 because package.json asks for >=22.12 (Astro 7 refuses to run on 20).
FROM node:22-alpine AS build

WORKDIR /app

# Dependencies first, so an edit to src/ reuses the cached npm layer.
# `npm ci` needs package-lock.json and installs exactly what it pins.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:22-alpine AS runtime

WORKDIR /app
ENV NODE_ENV=production

# Which build is answering /healthz. Baked in here rather than read from .env
# because both stacks share one .env file: a value set there would report the
# same number whichever container actually served the request.
#   1 = the Flask app in the repo root, 2 = this one.
ARG APP_VERSION=2
ARG APP_BUILD=unknown
ENV APP_VERSION=$APP_VERSION
ENV APP_BUILD=$APP_BUILD
# The adapter binds to HOST/PORT. 0.0.0.0 so the mapped port reaches it from
# outside the container; the published port stays bound to 127.0.0.1 on the
# host, where nginx is the only thing that can reach it.
ENV HOST=0.0.0.0
ENV PORT=5003

# --omit=dev leaves out the Astro CLI and friends; the built server only needs
# the runtime packages (@aws-sdk/client-s3, nodemailer, dotenv).
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY --from=build /app/dist ./dist

# Run unprivileged. The image ships with a `node` user for exactly this.
USER node

EXPOSE 5003

# No shell wrapper: node is PID 1 and receives SIGTERM directly, so a
# blue/green `docker rm -f` shuts the old container down cleanly.
CMD ["node", "./dist/server/entry.mjs"]
