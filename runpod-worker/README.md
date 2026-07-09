# SceneForge RunPod worker

Self-hosted generation on rented GPUs: FLUX.1-schnell (images) and
Wan2.1-I2V-14B-480P (image-to-video) running on a RunPod serverless
RTX 4090 for ~$0.10-0.15 per clip vs $0.80 hosted.

## How the pieces fit

```
sceneforge generate-clips --model runpod-wan-i2v
   │
   │  POST api.runpod.ai/v2/{endpoint}/run          (job in, image as base64)
   │  GET  api.runpod.ai/v2/{endpoint}/status/{id}  (poll until COMPLETED)
   ▼
RunPod serverless endpoint ──► spins up a worker (this Docker image)
                                 │ runpod.serverless.start(handler)
                                 │ loads model weights from the network
                                 │ volume (HF_HOME=/runpod-volume/…)
                                 │ runs diffusers inference on the GPU
                                 ▼
                               returns {"video_b64": ...} → client decodes
```

Billing is per-second while a worker runs (RTX 4090 flex ≈ $0.000306/s).
With min workers = 0 the endpoint scales to zero — you pay nothing idle
except network-volume storage. The client computes the real cost of every
artifact from the job's `executionTime` and stores it in project.json.

## One-time setup

1. **Account**: sign up at [runpod.io](https://runpod.io), add ~$10 credit.
   Settings → API Keys → create key → `RUNPOD_API_KEY` in `.env`.
2. **Registry**: any Docker registry works; Docker Hub free tier is fine
   (`docker login`).
3. **Network volume** (Console → Storage): 150 GB (~$10.50/month) in a
   datacenter that lists both RTX 4090 and RTX A6000 availability — the
   volume pins your endpoint to that datacenter.
4. **Build & push the worker** (from the repo root; cross-build since
   Apple Silicon ≠ RunPod's x86_64):

   ```bash
   docker buildx build --platform linux/amd64 \
     -t docker.io/<you>/sceneforge-worker:0.1 --push runpod-worker/
   ```

5. **Endpoint** (Console → Serverless → New Endpoint → Import from
   Docker Registry):
   - GPU priority: RTX 4090, then RTX A6000 (48 GB pressure valve —
     runs Wan-14B without CPU offload if 4090s are busy/slow)
   - Max workers **1** (cost control), active (min) workers 0
   - Idle timeout **120s** — keeps the loaded model warm between scenes
     in a batch (~$0.037/2min ≪ reloading 30 GB of weights)
   - Execution timeout **1800s** (cold load + 5-8 min generation)
   - FlashBoot on; attach the network volume
   - Copy the endpoint id → `RUNPOD_ENDPOINT_ID` in `.env`
6. **Warm the weight cache** (one-off, ~10-15 min ≈ $0.25 — downloads
   ~100 GB of model weights to the volume so cold starts load from disk):

   ```bash
   curl -s -X POST "https://api.runpod.ai/v2/$RUNPOD_ENDPOINT_ID/run" \
     -H "Authorization: Bearer $RUNPOD_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"input": {"task": "warmup"}}'
   # poll: curl .../status/<job_id> until COMPLETED
   ```

Then generate with `--model runpod-flux` / `--model runpod-wan-i2v`.
If the endpoint is down or misconfigured, SceneForge logs a warning and
falls back automatically (runpod-wan-i2v → seedance-2.0, runpod-flux →
flux-schnell).

## Worker internals

- `handler.py` — job dispatch: `{"task": "image" | "video" | "warmup"}`.
  Media travels base64 in the payload (10 MB `/run` cap; a PNG in and a
  5s 480p mp4 out both fit comfortably).
- `pipelines.py` — lazy loading, one pipeline resident at a time
  (24 GB can't hold FLUX and Wan-14B together); `enable_model_cpu_offload()`
  is mandatory for Wan-14B on a 4090.
- Output is **480p** (the 14B-480P model), upscaled at stitch time.
  Native 720p needs the 14B-720P variant on a 48 GB card.

Local dispatch check without a GPU:

```bash
python handler.py --test_input '{"input": {"task": "bogus"}}'   # → error path
```

## Cost reality check (estimates from verified pricing; measured numbers TBD)

| | Together (Seedance 2.0) | RunPod (Wan2.1 480P, 4090) |
|---|---|---|
| 5s clip, warm worker | $0.80 | ~$0.08-0.15 |
| 5s clip, cold start | $0.80 | ~$0.13-0.22 (includes model load) |
| Resolution | 720p | 480p |
| Wall time | 1-3 min | 5-10 min |
| Standing cost | none | $10.50/mo volume |
