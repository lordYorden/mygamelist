FROM node:22-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

COPY bff/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bff/app ./bff/app
COPY --from=frontend-build /frontend/dist ./frontend/dist

ENV PYTHONPATH=/app/bff
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
