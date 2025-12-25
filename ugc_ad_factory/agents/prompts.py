"""
Prompt Builder Agent - Creates image/video generation prompts for each shot.

Stage 5 of the UGC pipeline.
"""

import json
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..state import UGCPipelineState, AssetRequest, AssetStatus
from ..config import settings
from .utils import load_template, generate_id


PROMPTS_SYSTEM_PROMPT = """You are a prompt engineer specializing in AI image and video generation.

For each shot in the shot list, create prompts for:
1. ComfyUI/SDXL image generation (the still frame)
2. KeyAI Sora video motion (how the image animates)

Image prompts should be detailed, describing:
- Subject and composition
- Lighting and mood
- Style (commercial, UGC, professional, etc.)
- Camera angle and framing
- Quality tags (4K, commercial quality, etc.)

Video motion prompts should describe:
- Camera movement (slow zoom in, pan left, etc.)
- Any motion in the scene (product rotates, steam rises, etc.)
- Mood and pacing

Negative prompts should list what to avoid (text, watermarks, distortions, etc.)

Respond with a JSON array of asset requests:
[
    {
        "request_id": "req_001",
        "shot_id": "shot_001_01",
        "shotlist_id": "shotlist_001",
        "asset_type": "image",
        "backend": "comfyui",
        "prompt": "Commercial product photography of sleek white bottle...",
        "negative_prompt": "text, watermark, logo, blurry, distorted...",
        "width": 1080,
        "height": 1920,
        "style_preset": "commercial"
    },
    {
        "request_id": "req_002",
        "shot_id": "shot_001_01",
        "shotlist_id": "shotlist_001",
        "asset_type": "video",
        "backend": "keyai",
        "prompt": "Slow cinematic zoom in on the product, soft lighting shifts...",
        "duration_seconds": 3.0
    },
    ...
]

For each shot, create BOTH an image request (comfyui) and a video request (keyai).
The video will be generated from the image using image-to-video.
"""


async def build_prompts(state: UGCPipelineState) -> UGCPipelineState:
    """
    Stage 5: Build generation prompts for each shot.

    Creates AssetRequest objects for both image and video generation.
    Each shot gets an image prompt (ComfyUI) and a video motion prompt (KeyAI).
    """
    state.current_stage = "prompts"

    if state.error:
        return state

    if not state.shot_lists:
        state.error = "No shot lists available (shot planning stage failed?)"
        return state

    profile = state.product_profile

    # Try to load style presets
    try:
        style_templates = load_template(state.mode, "styles")
        styles = style_templates.get("visual_styles", [])
    except ValueError:
        styles = []

    # Build prompt with all shots
    shots_data = []
    for sl in state.shot_lists:
        for shot in sl.shots:
            shots_data.append({
                "shot_id": shot.shot_id,
                "shotlist_id": sl.shotlist_id,
                "shot_type": shot.shot_type,
                "duration_seconds": shot.duration_seconds,
                "description": shot.description,
                "camera_movement": shot.camera_movement,
                "subject": shot.subject,
                "background": shot.background,
                "lighting": shot.lighting,
            })

    user_prompt = f"""Create generation prompts for these {len(shots_data)} shots:

Product: {profile.name}
Category: {profile.category}
Visual Tone: {profile.tone}
Brand Colors: {profile.brand_colors or 'not specified'}

{"Available style presets:" if styles else ""}
{json.dumps(styles, indent=2) if styles else ""}

Shots to generate:
{json.dumps(shots_data, indent=2)}

For EACH shot, create:
1. An image prompt for ComfyUI (backend: "comfyui", asset_type: "image")
2. A video motion prompt for KeyAI Sora (backend: "keyai", asset_type: "video")

All images should be 1080x1920 (9:16 vertical for short-form video).
Video durations should match the shot's duration_seconds."""

    try:
        llm = ChatAnthropic(
            model=settings.llm_model,
            api_key=settings.anthropic_api_key,
            max_tokens=32000,
        )

        messages = [
            SystemMessage(content=PROMPTS_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = await llm.ainvoke(messages)

        # Parse JSON response
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        requests_data = json.loads(content.strip())

        # Create AssetRequest objects
        state.asset_requests = []
        for i, req_data in enumerate(requests_data):
            request = AssetRequest(
                request_id=req_data.get("request_id", generate_id("req", i)),
                shot_id=req_data.get("shot_id", ""),
                shotlist_id=req_data.get("shotlist_id", ""),
                asset_type=req_data.get("asset_type", "image"),
                backend=req_data.get("backend", "comfyui"),
                prompt=req_data.get("prompt", ""),
                negative_prompt=req_data.get("negative_prompt", ""),
                width=req_data.get("width", 1080),
                height=req_data.get("height", 1920),
                duration_seconds=req_data.get("duration_seconds"),
                style_preset=req_data.get("style_preset", "default"),
                status=AssetStatus.PENDING,
            )
            state.asset_requests.append(request)

        # Count by type
        image_count = sum(1 for r in state.asset_requests if r.asset_type == "image")
        video_count = sum(1 for r in state.asset_requests if r.asset_type == "video")
        state.warnings.append(
            f"Created {len(state.asset_requests)} asset requests ({image_count} images, {video_count} videos)"
        )

    except json.JSONDecodeError as e:
        state.error = f"Failed to parse prompts response: {str(e)}"
    except Exception as e:
        state.error = f"Prompt building failed: {str(e)}"

    return state
