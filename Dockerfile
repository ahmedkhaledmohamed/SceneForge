# SceneForge full-stack: FastAPI + React SPA + ffmpeg
# Deploy to Railway/Render/Fly.io with a persistent volume at /data

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl ca-certificates gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY frontend/ frontend/

# Build frontend → src/sceneforge/web_dist/
RUN cd frontend && npm ci --no-audit --no-fund && npm run build

# Editable install so web_dist (static files) is found at runtime
RUN pip install --no-cache-dir -e .

# Ensure data dir exists even without a volume mount
RUN mkdir -p /data

ENV SCENEFORGE_HOME=/data
ENV PORT=8000
EXPOSE 8000

CMD python -c "\
from sceneforge.server import create_app_from_env; \
import uvicorn; \
uvicorn.run(create_app_from_env(), host='0.0.0.0', port=int(__import__('os').environ.get('PORT', 8000)))"
