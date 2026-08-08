# ============================================================================
# Sonani web (React + Vite) — production image.
# Build the static bundle with Node, then serve it from nginx. The final image
# is just nginx + a few hundred KB of hashed assets — no Node at runtime.
# ============================================================================

# ---- Stage 1: build --------------------------------------------------------
FROM node:20-alpine AS build
WORKDIR /app

# Install deps against the lockfile for reproducible builds.
COPY package*.json ./
RUN npm ci

COPY . .
# VITE_* vars are baked in at build time. Default to same-origin "/api" so nginx
# can proxy; override with --build-arg VITE_API_URL=... for a split deployment.
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# ---- Stage 2: serve --------------------------------------------------------
FROM nginx:1.27-alpine AS runtime
# Run nginx as the unprivileged built-in user.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost/healthz >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
