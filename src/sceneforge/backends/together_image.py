"""Together AI image generation (FLUX family) via the REST endpoint.

Ported from the proven MiseEnPlace pattern: POST to
/v1/images/generations, read data[0].url with a b64_json fallback.
"""

import base64
import json
import urllib.request

from ..config import TOGETHER_BASE_URL, together_api_key
from ..util import download
from .base import ImageBackend, ImageResult


class TogetherImageBackend(ImageBackend):
    def generate_image(self, prompt, out_path, *, width, height,
                       reference_image=None, seed=None):
        body = {
            "model": self.model["id"],
            "prompt": prompt,
            "n": 1,
            "width": width,
            "height": height,
            "steps": self.model.get("steps", 4),
        }
        if seed is not None:
            body["seed"] = seed
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

        return ImageResult(
            path=out_path,
            prompt=prompt,
            model=self.model["key"],
            meta={"seed": seed, "steps": body["steps"]},
        )
