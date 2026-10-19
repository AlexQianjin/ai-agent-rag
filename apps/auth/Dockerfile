# Build context is the repository root so the pnpm lockfile is available.
FROM node:22-bookworm-slim

WORKDIR /app

ENV CI=true \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0

RUN corepack enable && corepack prepare pnpm@10.33.4 --activate

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/auth/package.json apps/auth/package.json
COPY apps/frontend/package.json apps/frontend/package.json
COPY apps/backend/package.json apps/backend/package.json

RUN pnpm install --frozen-lockfile --filter auth...

COPY apps/auth apps/auth

WORKDIR /app/apps/auth

ENV PORT=3001
EXPOSE 3001

CMD ["pnpm", "start"]
