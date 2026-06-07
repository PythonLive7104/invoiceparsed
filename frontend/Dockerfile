# InvoiceParsed frontend — build the Vite SPA, serve it (and proxy /api) via nginx.

# ── Build stage ──────────────────────────────────────────────────────────────
FROM node:20-alpine AS build
WORKDIR /app

COPY package*.json ./
# --legacy-peer-deps: the project pins vite 8 against @vitejs/plugin-react's
# older peer range (the repo already lives with this).
RUN npm ci --legacy-peer-deps

COPY . .

# Empty = same-origin: the browser calls /api on this host and nginx proxies it
# to the backend. Override at build time for a split frontend/API domain setup.
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# ── Runtime stage ────────────────────────────────────────────────────────────
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
