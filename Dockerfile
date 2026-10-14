# Production image: FastAPI serving the API and the built React app on port 8000.
# The same image runs the worker (`python -m app.worker`), migrations and the seed.

FROM node:24-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
# uv and its download cache are mounted only for this step, so neither ends up in the image.
RUN --mount=from=ghcr.io/astral-sh/uv:0.9.3,source=/uv,target=/usr/local/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY backend/scripts ./scripts
COPY --from=frontend /frontend/dist /app/frontend/dist

RUN useradd --system --uid 1000 --home-dir /app acme && mkdir -p /data/storage \
    && chown acme /data/storage
USER acme
ENV FRONTEND_DIST=/app/frontend/dist STORAGE_DIR=/data/storage
# Last, so a new commit doesn't rebuild the layers above. /health reports it.
ARG GIT_COMMIT
ENV GIT_COMMIT=$GIT_COMMIT
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
