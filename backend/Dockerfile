# MatchMind backend: FastAPI streamer + Interpreter + Risk Monitor + agents + MCP.
# Build context is backend/. Secrets come from the environment (Container Apps secrets), never the image.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    MATCHMIND_DATA_DIR=/data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY matchmind ./matchmind

# The default match is generated on first start if /data is empty (see api/app.py lifespan).
RUN mkdir -p /data

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "matchmind.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
