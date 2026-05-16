# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Next.js 15 (App Router) — pnpm monorepo standalone build
# Build context: monorepo root (services/backend/docker-compose.yml passes ../..)
# ---------------------------------------------------------------------------

ARG NODE_VERSION=20-alpine
ARG PNPM_VERSION=9.12.0

# ===========================================================================
# Stage 1: deps  — install workspace dependencies (cache-friendly)
# ===========================================================================
FROM node:${NODE_VERSION} AS deps
ARG PNPM_VERSION
WORKDIR /app

# Alpine essentials for some native modules (sharp, etc.)
RUN apk add --no-cache libc6-compat

# Enable corepack and pin pnpm version (matches root packageManager field)
RUN corepack enable && corepack prepare pnpm@${PNPM_VERSION} --activate

# Copy workspace manifests first for better layer caching
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/
COPY packages/types/package.json ./packages/types/
COPY packages/ui/package.json ./packages/ui/

# Install only the deps needed for the web app + its workspace siblings
RUN --mount=type=cache,id=pnpm,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile \
      --filter @arac-hasar/web... \
      --filter @arac-hasar/ui \
      --filter @arac-hasar/types

# ===========================================================================
# Stage 2: builder — copy source, run next build (produces standalone bundle)
# ===========================================================================
FROM node:${NODE_VERSION} AS builder
ARG PNPM_VERSION
WORKDIR /app

RUN apk add --no-cache libc6-compat
RUN corepack enable && corepack prepare pnpm@${PNPM_VERSION} --activate

# Bring in fully installed node_modules graph from deps stage
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules
COPY --from=deps /app/packages/types/node_modules ./packages/types/node_modules
COPY --from=deps /app/packages/ui/node_modules ./packages/ui/node_modules

# Copy workspace manifests + source
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json ./
COPY apps/web ./apps/web
COPY packages/types ./packages/types
COPY packages/ui ./packages/ui

# Public env is *baked* at build time (Next.js NEXT_PUBLIC_*)
# Default points at host-mapped backend so the browser can reach it.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

# Build the web app — standalone output lands in apps/web/.next/standalone
RUN pnpm --filter @arac-hasar/web build

# ===========================================================================
# Stage 3: runner — minimal production image
# ===========================================================================
FROM node:${NODE_VERSION} AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

RUN apk add --no-cache wget \
 && addgroup --system --gid 1001 nodejs \
 && adduser  --system --uid 1001 nextjs

# Copy standalone server (self-contained Node bundle that includes
# the minimal node_modules graph, including workspace packages).
# Standalone places the server.js inside apps/web/ when built from a monorepo.
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/static       ./apps/web/.next/static
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/public             ./apps/web/public

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD wget -qO- http://localhost:3000/api/health || exit 1

# server.js sits next to the apps/web directory in the standalone output
CMD ["node", "apps/web/server.js"]
