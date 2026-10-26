# MatchMind backend: FastAPI streamer + Interpreter + Risk Monitor + Agent Framework agents + MCP.
# Build context is backend/. No secrets in the image: Foundry is reached with a managed identity and the
# Speech key arrives as a Container Apps secret (Key Vault reference). Pinned base image, pinned
# dependencies (requirements.lock), non-root user.
FROM python:3.11-slim@sha256:b7a9e5f6a93d6d4a31f129bbd4bdee69efccb6ded0fb230d78aafaf37af98377

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    MATCHMIND_DATA_DIR=/data \
    OTEL_SERVICE_NAME=matchmind-api

WORKDIR /app

COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY matchmind ./matchmind

# /data is an Azure Files mount in Container Apps (matches, warmed agent cache, TTS cache); the default
# match is generated on first start if it is empty (see api/app.py lifespan).
RUN useradd -r -u 10001 -d /app app && mkdir -p /data && chown app:app /data
USER app

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "matchmind.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
