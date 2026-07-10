"""Together AI image generation (FLUX family) via the REST endpoint.

Ported from the proven MiseEnPlace pattern: POST to
/v1/images/generations, read data[0].url with a b64_json fallback.
"""

import base64
import json
import urllib.request

from ..config import TOGETHER_BASE_URL, together_api_key
from ..util import download, image_data_uri
from .base import ImageBackend, ImageResult


class TogetherImageBackend(ImageBackend):
    def generate_image(self, prompt, out_path, *, width, height,
                       reference_images=None, seed=None):
        # n is deliberately omitted: 1 is the default, and Together's
        # Gemini-image relay rejects the parameter outright.
        body = {
            "model": self.model["id"],
            "prompt": prompt,
            "width": width,
            "height": height,
        }
        if "steps" in self.model:
            body["steps"] = self.model["steps"]
        if seed is not None:
            body["seed"] = seed
        if reference_images:
            # Multi-reference conditioning (FLUX.2 family and Gemini image
            # models on Together). Images travel inline as data URIs.
            body["reference_images"] = [image_data_uri(p) for p in reference_images]
        req = urllib.request.Request(
            f"{TOGETHER_BASE_URL}/images/generations",
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {together_api_key()}",
                "Content-Type": "application/json",
                # Cloudflare 403s urllib's default Python-urllib agent
                "User-Agent": "SceneForge/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())

        entry = result["data"][0]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if entry.get("url"):
            download(entry["url"], out_path)
        elif entry.get("b64_json"):
            out_path.write_bytes(base64.b64decode(entry["b64_json"]))
        else:
            raise RuntimeError(f"No image in response: {list(entry.keys())}")

        meta = {"seed": seed}
        if "steps" in body:
            meta["steps"] = body["steps"]
        if reference_images:
            meta["reference_images"] = [str(p) for p in reference_images]
        return ImageResult(
            path=out_path,
            prompt=prompt,
            model=self.model["key"],
            meta=meta,
        )
