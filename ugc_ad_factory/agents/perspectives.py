"""
Perspective Planning Agent - Plans different perspectives/views to generate.

Takes source product images and plans what perspectives to generate
for creating smooth, natural transitions in the final video.
"""

import json
import uuid
from typing import Any

from anthropic import Anthropic

from ..state import (
    UGCPipelineState,
    SourceImage,
    Perspective,
    GeneratedPerspective,
    AssetStatus,
)
from ..config import settings


# Perspective types that work well for product videos
PERSPECTIVE_TYPES = [
    "hero_front",      # Main front-facing hero shot
    "angle_45",        # 45-degree angle view
    "angle_side",      # Side profile view
    "close_up_detail", # Close-up on product detail/texture
    "top_down",        # Bird's eye / overhead view
    "low_angle",       # Looking up at product (dramatic)
    "lifestyle",       # Product in use/context
    "packaging",       # Product with packaging
    "macro_texture",   # Extreme close-up on material/texture
    "environment",     # Product in environment (kitchen, desk, etc.)
]


PERSPECTIVE_PLANNER_PROMPT = """You are a creative director for product advertisement videos.

Given the product information and source images, plan a sequence of perspectives that will:
1. Start with the source image as-is (or very close to it)
2. Generate new perspectives that transition naturally from one to the next
3. Create visual interest through varied angles, zoom levels, and compositions
4. End with a strong final shot (hero or lifestyle)

The perspectives should flow naturally so that when animated, the transitions look smooth.

**Product Information:**
- Name: {product_name}
- Description: {product_description}
- Style: {product_style}

**Source Images Available:**
{source_images_info}

**Guidelines:**
- Plan 4-8 perspectives total (including the starting source image)
- Each perspective should be achievable via img2img from the source
- Order perspectives for natural visual flow (e.g., wide → detail → wide)
- Consider the product type - what angles showcase it best?
- For e-commerce products: focus on product details, features, quality
- For local business: include environment/context shots
- Keep descriptions concise but specific enough for image generation

Return a JSON array of perspectives:
```json
[
  {{
    "perspective_id": "persp_001",
    "source_image_id": "img_001",
    "view_type": "hero_front",
    "description": "Front-facing hero shot of the product...",
    "camera_angle": "front",
    "zoom_level": "medium",
    "lighting_style": "studio",
    "background_hint": "clean white background",
    "sequence_order": 0
  }},
  ...
]
```

Respond with ONLY the JSON array, no other text.
"""


async def plan_perspectives(state: UGCPipelineState) -> UGCPipelineState:
    """
    Stage: Perspective Planning

    Analyzes source images and plans the sequence of perspectives to generate.
    Each perspective builds on a source image via img2img transformation.
    """
    state.current_stage = "perspectives"

    if state.error:
        return state

    if not state.source_images:
        state.error = "No source images provided"
        return state

    # Build source images info for prompt
    source_images_info = "\n".join([
        f"- {img.image_id}: {img.description or 'No description'} "
        f"{'(PRIMARY)' if img.is_primary else ''}"
        for img in state.source_images
    ])

    # Call LLM to plan perspectives
    client = Anthropic(api_key=settings.anthropic_api_key)

    prompt = PERSPECTIVE_PLANNER_PROMPT.format(
        product_name=state.product_name or "Product",
        product_description=state.product_description or "A product",
        product_style=state.product_style or "clean",
        source_images_info=source_images_info,
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        response_text = response.content[0].text

        # Parse JSON response
        # Try to extract JSON from response
        json_start = response_text.find("[")
        json_end = response_text.rfind("]") + 1
        if json_start >= 0 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            perspectives_data = json.loads(json_str)
        else:
            raise ValueError("No JSON array found in response")

        # Convert to Perspective objects
        perspectives = []
        for i, p_data in enumerate(perspectives_data):
            perspective = Perspective(
                perspective_id=p_data.get("perspective_id", f"persp_{i:03d}"),
                source_image_id=p_data.get("source_image_id", state.source_images[0].image_id),
                view_type=p_data.get("view_type", "hero_front"),
                description=p_data.get("description", ""),
                camera_angle=p_data.get("camera_angle", "front"),
                zoom_level=p_data.get("zoom_level", "medium"),
                lighting_style=p_data.get("lighting_style", "studio"),
                background_hint=p_data.get("background_hint", ""),
                sequence_order=p_data.get("sequence_order", i),
            )
            perspectives.append(perspective)

        # Sort by sequence order
        perspectives.sort(key=lambda p: p.sequence_order)

        state.perspectives = perspectives
        state.warnings.append(f"Planned {len(perspectives)} perspectives")

        # Initialize generated_perspectives with pending status
        state.generated_perspectives = [
            GeneratedPerspective(
                perspective_id=p.perspective_id,
                source_image_id=p.source_image_id,
                status=AssetStatus.PENDING,
            )
            for p in perspectives
        ]

    except json.JSONDecodeError as e:
        state.error = f"Failed to parse perspective plan: {e}"
    except Exception as e:
        state.error = f"Perspective planning failed: {e}"

    return state


async def analyze_source_images(state: UGCPipelineState) -> UGCPipelineState:
    """
    Stage: Analyze source images and set up for perspective generation.

    This is the intake stage for perspective-based mode.
    Downloads/validates source images and prepares them for processing.
    """
    state.current_stage = "intake"

    if state.error:
        return state

    # Source images should already be populated from raw_input
    product_images = state.raw_input.get("product_images", [])

    if not product_images:
        state.error = "No product images provided in raw_input"
        return state

    # Convert to SourceImage objects if not already
    if not state.source_images:
        source_images = []
        for i, img_url in enumerate(product_images):
            source_images.append(SourceImage(
                image_id=f"src_{i:03d}",
                url=img_url,
                description=state.raw_input.get("image_descriptions", {}).get(str(i), ""),
                is_primary=(i == 0),
            ))
        state.source_images = source_images

    # Extract product info
    state.product_name = state.raw_input.get("product_name", "Product")
    state.product_description = state.raw_input.get("product_description", "")
    state.product_style = state.raw_input.get("product_style", "clean")

    state.warnings.append(f"Loaded {len(state.source_images)} source images")

    return state
