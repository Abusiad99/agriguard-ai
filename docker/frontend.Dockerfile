# AgriGuard AI — Frontend Dockerfile
#
# Multi-stage build: Stage 1 compiles the Vite/React/TypeScript app; the resulting
# static `dist/` output is the only thing that leaves this image. The `nginx`
# service in docker-compose.yml mounts that output directly (via the shared
# `frontend_dist` named volume) and serves it as static files — there is no
# Node.js runtime in the production path, and no separate frontend "server"
# container (NFR-PORT-1: the whole stack is `docker compose up`-able).

# ---------------------------------------------------------------------------
# Stage 1: build
# ---------------------------------------------------------------------------
FROM node:20-alpine AS build

WORKDIR /app

COPY frontend/package*.json ./
RUN npm ci || npm install

COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: export static assets into the shared volume
# ---------------------------------------------------------------------------
# This stage's only job is to copy the build output somewhere `docker compose`
# can mount as a volume for the `nginx` service. Using a minimal alpine base
# (not nginx itself) since this container never runs long-term — it exits
# immediately after the copy via docker-compose's `frontend` service definition.
FROM alpine:3.20 AS export

COPY --from=build /app/dist /dist

CMD ["sh", "-c", "cp -r /dist/. /output/ && echo 'Frontend build exported to /output'"]
