"""Automatic backend fallback: try the primary, delegate to the fallback
on any failure, tagging the result so artifacts record what happened.
Wired by the factory when a registry entry has a "fallback" key."""

from .base import ImageBackend, VideoBackend


class FallbackImageBackend(ImageBackend):
    def __init__(self, primary: ImageBackend, fallback: ImageBackend, log=print):
        super().__init__(primary.model)
        self.primary = primary
        self.fallback = fallback
        self.log = log
        # max_reference_images comes from self.model (copied from primary)

    def generate_image(self, prompt, out_path, **kwargs):
        try:
            return self.primary.generate_image(prompt, out_path, **kwargs)
        except Exception as exc:
            self.log(
                f"WARNING: {self.primary.model['key']} failed ({exc}) — "
                f"falling back to {self.fallback.model['key']}"
            )
            result = self.fallback.generate_image(prompt, out_path, **kwargs)
            result.meta["fallback_from"] = self.primary.model["key"]
            return result


class FallbackVideoBackend(VideoBackend):
    def __init__(self, primary: VideoBackend, fallback: VideoBackend, log=print):
        super().__init__(primary.model)
        self.primary = primary
        self.fallback = fallback
        self.log = log
        self.supports_i2v = primary.supports_i2v

    def generate_clip(self, prompt, out_path, **kwargs):
        try:
            return self.primary.generate_clip(prompt, out_path, **kwargs)
        except Exception as exc:
            self.log(
                f"WARNING: {self.primary.model['key']} failed ({exc}) — "
                f"falling back to {self.fallback.model['key']}"
            )
            result = self.fallback.generate_clip(prompt, out_path, **kwargs)
            result.meta["fallback_from"] = self.primary.model["key"]
            return result
