# SceneForge full-stack: FastAPI + React SPA + ffmpeg
# Deploy to Railway/Render/Fly.io with a persistent volume at /data

FROM python:3.14-slim

# ffmpeg for stitching + curl for Together CDN downloads
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl && rm -rf /var/lib/apt/lists/*

# Node.js for frontend build
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps first (cache layer)
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir -e .

# Frontend build
COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci --no-audit --no-fund
COPY frontend/ frontend/
RUN cd frontend && npm run build

# The volume mount point — profiles, projects, and generated media
ENV SCENEFORGE_HOME=/data
VOLUME /data

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "sceneforge.server:create_app_from_env", \
     "--host", "0.0.0.0", "--port", "8000", "--factory"]
