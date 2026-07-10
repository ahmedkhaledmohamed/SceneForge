"""Thin HTTP client for the RunPod serverless API.

The whole API surface SceneForge needs is three routes
(https://docs.runpod.io/serverless/endpoints/operation-reference):

  POST /v2/{endpoint_id}/run              submit async job (10 MB payload cap)
  GET  /v2/{endpoint_id}/status/{job_id}  poll: IN_QUEUE|IN_PROGRESS|COMPLETED|FAILED,
                                          plus output, delayTime/executionTime (ms)
  GET  /v2/{endpoint_id}/health           worker/job counts

Deliberately raw urllib rather than the runpod SDK — seeing the actual
HTTP is the point. The `http` callable is injectable for tests.
"""

import json
import urllib.error
import urllib.request

API_BASE = "https://api.runpod.ai/v2"


class RunPodUnavailableError(RuntimeError):
    """Endpoint unreachable or misconfigured — triggers backend fallback."""


def _default_http(url: str, api_key: str, payload: dict | None = None,
                  timeout: float = 60) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "SceneForge/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404) or exc.code >= 500:
            raise RunPodUnavailableError(f"RunPod API {exc.code} for {url}") from exc
        raise
    except urllib.error.URLError as exc:
        raise RunPodUnavailableError(f"RunPod unreachable: {exc.reason}") from exc


class RunPodClient:
    def __init__(self, endpoint_id: str, api_key: str, http=_default_http):
        self.endpoint_id = endpoint_id
        self.api_key = api_key
        self._http = http

    def run(self, input_payload: dict) -> str:
        """Submit a job; returns the job id."""
        data = self._http(
            f"{API_BASE}/{self.endpoint_id}/run", self.api_key,
            payload={"input": input_payload},
        )
        return data["id"]

    def status(self, job_id: str) -> dict:
        return self._http(
            f"{API_BASE}/{self.endpoint_id}/status/{job_id}", self.api_key
        )

    def health(self) -> dict:
        return self._http(f"{API_BASE}/{self.endpoint_id}/health", self.api_key)
