# SceneForge RunPod serverless worker.
#
# Build on Apple Silicon (RunPod GPUs are x86_64, so cross-build):
#   docker buildx build --platform linux/amd64 \
#     -t docker.io/<you>/sceneforge-worker:0.1 --push runpod-worker/
#
# The base image ships PyTorch 2.8 + CUDA 12.8, saving a ~5 GB pip
# install and matching RunPod's host drivers.
FROM runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY handler.py pipelines.py .

# Model weights cache on the attached network volume — cold starts load
# from disk instead of re-downloading ~100 GB (see the warmup task).
ENV HF_HOME=/runpod-volume/huggingface-cache

CMD ["python", "-u", "handler.py"]
