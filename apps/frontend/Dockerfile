# Build the Vite app from the repository root so the pnpm workspace
# lockfile is available, then serve the static files with nginx.
FROM node:22-bookworm-slim AS build

WORKDIR /app

ARG VITE_AUTH_URL=http://localhost:8080
ARG VITE_API_URL=
ENV VITE_AUTH_URL=$VITE_AUTH_URL \
    VITE_API_URL=$VITE_API_URL \
    CI=true \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0

RUN corepack enable && corepack prepare pnpm@10.33.4 --activate

# The lockfile lists every workspace package, including the backend script package.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/frontend/package.json apps/frontend/package.json
COPY apps/backend/package.json apps/backend/package.json
COPY apps/auth/package.json apps/auth/package.json

RUN pnpm install --frozen-lockfile

COPY apps/frontend apps/frontend

RUN pnpm --filter frontend build

FROM nginx:1.28-alpine

COPY apps/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/frontend/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
