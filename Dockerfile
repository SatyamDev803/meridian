# Stage 1: build the dashboard as static files.
FROM node:22-alpine AS web
WORKDIR /web
RUN npm i -g pnpm@10.0.0
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
ENV NEXT_PUBLIC_API_BASE=""
RUN pnpm build

# Stage 2: the Python service that trades and serves the dashboard.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
COPY meridian ./meridian
RUN pip install .
COPY --from=web /web/out ./web/out
ENV HOST=0.0.0.0 PORT=8000 WEB_DIR=/app/web/out
EXPOSE 8000
CMD ["python", "-m", "meridian"]
