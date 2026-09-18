# Stage 1: build the operator console (frontend/src imports tests/fixtures/public_cases.json)
FROM node:22-slim AS console
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
COPY tests/fixtures/ /build/tests/fixtures/
RUN npm run build

# Stage 2: the API
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY --from=console /build/frontend/dist ./frontend/dist

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
# Hosting platforms inject PORT; locally it defaults to 8000. No secrets are baked in: pass them with -e.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
