"""LLM-assisted scene breakdown: concept + style anchor -> N scene
descriptions, each a single static visual moment suitable for one image."""

import json
import re

from .config import DEFAULT_LLM_MODEL, TOGETHER_BASE_URL, together_api_key

SYSTEM_PROMPT = (
    "You are a video storyboard writer for short vertical social videos "
    "(Reels/TikTok). Respond with JSON only, no commentary."
)

USER_TEMPLATE = """Concept: {concept}
Visual style: {anchor}

Break this concept into exactly {count} scenes for a short vertical video.

Rules for each scene:
- One static visual moment, fully describable in a single image
- No camera movement, no cuts, no text or captions
- Present tense, concrete subjects and actions, 15-30 words
- Scenes flow in a natural narrative order

Output exactly this JSON shape:
{{"scenes": [{{"description": "..."}}]}}"""


def generate_scenes(concept: str, anchor: str, count: int = 6,
                    model: str = DEFAULT_LLM_MODEL) -> list[str]:
    from openai import OpenAI

    client = OpenAI(api_key=together_api_key(), base_url=TOGETHER_BASE_URL)
    user_prompt = USER_TEMPLATE.format(concept=concept, anchor=anchor, count=count)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    last_error = None
    for _ in range(2):
        response = client.chat.completions.create(
            model=model, messages=messages, temperature=0.7
        )
        raw = response.choices[0].message.content
        try:
            return _parse_scenes(raw)
        except ValueError as exc:
            last_error = exc
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": f"That was invalid ({exc}). Output only the JSON object.",
            })
    raise ValueError(f"Scene breakdown failed after retry: {last_error}")


def _parse_scenes(raw: str) -> list[str]:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # tolerate leading/trailing prose around the JSON object
    if not text.startswith("{"):
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON object found in: {raw[:200]}")
        text = match.group(0)

    data = json.loads(text)
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("Expected a non-empty 'scenes' array")
    descriptions = []
    for i, scene in enumerate(scenes):
        desc = scene.get("description") if isinstance(scene, dict) else None
        if not isinstance(desc, str) or not desc.strip():
            raise ValueError(f"Scene {i + 1} has no description")
        descriptions.append(desc.strip())
    return descriptions
