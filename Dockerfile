# SceneForge full-stack: FastAPI + React SPA + ffmpeg
# Deploy to Railway/Render/Fly.io with a persistent volume at /data

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl ca-certificates gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy everything needed
COPY pyproject.toml .
COPY src/ src/
COPY frontend/ frontend/

# Build frontend → src/sceneforge/web_dist/
RUN cd frontend && npm ci --no-audit --no-fund && npm run build

# Install Python package (includes built web_dist)
RUN pip install --no-cache-dir .

ENV SCENEFORGE_HOME=/data
# Volume mounted via platform (Railway/Render dashboard), not Dockerfile
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "sceneforge.server:create_app_from_env", \
     "--host", "0.0.0.0", "--port", "8000", "--factory"]
