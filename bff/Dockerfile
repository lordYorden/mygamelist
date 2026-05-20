FROM node:22-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.9.13 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY bff/pyproject.toml bff/uv.lock ./
RUN uv sync --frozen --no-dev

COPY bff/app ./bff/app
COPY --from=frontend-build /frontend/dist ./frontend/dist

ENV PYTHONPATH=/app/bff
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
