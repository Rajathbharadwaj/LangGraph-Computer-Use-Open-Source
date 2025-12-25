"""
Transition Planning Agent - Plans transitions between perspectives.

Creates start→end frame pairs that will be animated via I2V (image-to-video).
This is key for the "Nano Banana" style smooth product transitions.
"""

import json
import uuid
from typing import Any

from anthropic import Anthropic

from ..state import (
    UGCPipelineState,
    Perspective,
    GeneratedPerspective,
    Transition,
    GeneratedTransition,
    AssetStatus,
)
from ..config import settings


# Motion types for transitions
MOTION_TYPES = [
    "smooth",       # Gentle, smooth transition
    "zoom_in",      # Camera zooms in toward subject
    "zoom_out",     # Camera zooms out from subject
    "pan_left",     # Camera pans left
    "pan_right",    # Camera pans right
    "orbit_left",   # Camera orbits around subject (left)
    "orbit_right",  # Camera orbits around subject (right)
    "tilt_up",      # Camera tilts up
    "tilt_down",    # Camera tilts down
    "push_in",      # Dolly in toward subject
    "reveal",       # Dramatic reveal transition
]


TRANSITION_PLANNER_PROMPT = """You are a video editor planning smooth transitions between product shots.

Given a sequence of perspectives (start and end frames), plan the motion/animation
that should happen between each pair. The goal is to create fluid, professional-looking
transitions like you'd see in premium product advertisements.

**Product Context:**
- Name: {product_name}
- Description: {product_description}
- Style: {product_style}

**Perspectives in Sequence:**
{perspectives_info}

**Guidelines:**
- Each transition connects two adjacent perspectives
- Motion should feel natural and intentional
- Consider the visual similarity between frames when choosing motion
- Smooth/orbit motions work well for similar angles
- Zoom works well when changing from wide to close-up or vice versa
- Duration should be 2-4 seconds for most transitions
- Total video should be around 10-20 seconds

Return a JSON array of transitions:
```json
[
  {{
    "transition_id": "trans_001",
    "start_perspective_id": "persp_000",
    "end_perspective_id": "persp_001",
    "motion_type": "smooth",
    "motion_description": "Camera smoothly tracks from front view to 45-degree angle",
    "duration_seconds": 2.5,
    "easing": "ease_in_out"
  }},
  ...
]
```

Respond with ONLY the JSON array, no other text.
"""


async def plan_transitions(state: UGCPipelineState) -> UGCPipelineState:
    """
    Stage: Transition Planning

    Takes the sequence of perspectives and plans the transitions between them.
    Each transition will be animated using I2V (start frame → end frame).
    """
    state.current_stage = "transitions"

    if state.error:
        return state

    if not state.perspectives:
        state.error = "No perspectives available for transition planning"
        return state

    # Need at least 2 perspectives for transitions
    if len(state.perspectives) < 2:
        state.warnings.append("Only 1 perspective - no transitions needed")
        state.transitions = []
        return state

    # Build perspectives info for prompt
    perspectives_info = []
    sorted_perspectives = sorted(state.perspectives, key=lambda p: p.sequence_order)

    for i, p in enumerate(sorted_perspectives):
        perspectives_info.append(
            f"{i+1}. [{p.perspective_id}] {p.view_type}: {p.description} "
            f"(angle: {p.camera_angle}, zoom: {p.zoom_level})"
        )

    # Call LLM to plan transitions
    client = Anthropic(api_key=settings.anthropic_api_key)

    prompt = TRANSITION_PLANNER_PROMPT.format(
        product_name=state.product_name or "Product",
        product_description=state.product_description or "A product",
        product_style=state.product_style or "clean",
        perspectives_info="\n".join(perspectives_info),
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
        json_start = response_text.find("[")
        json_end = response_text.rfind("]") + 1
        if json_start >= 0 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            transitions_data = json.loads(json_str)
        else:
            # Generate default transitions if LLM response is malformed
            transitions_data = _generate_default_transitions(sorted_perspectives)

        # Convert to Transition objects
        transitions = []
        for i, t_data in enumerate(transitions_data):
            transition = Transition(
                transition_id=t_data.get("transition_id", f"trans_{i:03d}"),
                start_perspective_id=t_data.get("start_perspective_id"),
                end_perspective_id=t_data.get("end_perspective_id"),
                motion_type=t_data.get("motion_type", "smooth"),
                motion_description=t_data.get("motion_description", ""),
                duration_seconds=float(t_data.get("duration_seconds", 2.5)),
                easing=t_data.get("easing", "ease_in_out"),
            )
            transitions.append(transition)

        state.transitions = transitions
        state.warnings.append(f"Planned {len(transitions)} transitions")

        # Initialize generated_transitions with pending status
        state.generated_transitions = [
            GeneratedTransition(
                transition_id=t.transition_id,
                start_image_url="",  # Will be filled after perspective generation
                end_image_url="",
                duration_seconds=t.duration_seconds,
                status=AssetStatus.PENDING,
            )
            for t in transitions
        ]

    except json.JSONDecodeError as e:
        # Fall back to default transitions
        state.warnings.append(f"LLM response parse failed, using defaults: {e}")
        transitions = _generate_default_transitions(sorted_perspectives)
        state.transitions = transitions

        state.generated_transitions = [
            GeneratedTransition(
                transition_id=t.transition_id,
                start_image_url="",
                end_image_url="",
                duration_seconds=t.duration_seconds,
                status=AssetStatus.PENDING,
            )
            for t in transitions
        ]

    except Exception as e:
        state.error = f"Transition planning failed: {e}"

    return state


def _generate_default_transitions(perspectives: list[Perspective]) -> list[Transition]:
    """Generate default transitions between consecutive perspectives."""
    transitions = []

    for i in range(len(perspectives) - 1):
        start = perspectives[i]
        end = perspectives[i + 1]

        # Infer motion type from perspective changes
        motion_type = _infer_motion_type(start, end)

        transitions.append(Transition(
            transition_id=f"trans_{i:03d}",
            start_perspective_id=start.perspective_id,
            end_perspective_id=end.perspective_id,
            motion_type=motion_type,
            motion_description=f"Transition from {start.view_type} to {end.view_type}",
            duration_seconds=2.5,
            easing="ease_in_out",
        ))

    return transitions


def _infer_motion_type(start: Perspective, end: Perspective) -> str:
    """Infer the best motion type based on perspective changes."""
    # Zoom level changes
    zoom_order = {"wide": 0, "medium": 1, "close": 2}
    start_zoom = zoom_order.get(start.zoom_level, 1)
    end_zoom = zoom_order.get(end.zoom_level, 1)

    if end_zoom > start_zoom:
        return "zoom_in"
    elif end_zoom < start_zoom:
        return "zoom_out"

    # Angle changes
    if start.camera_angle != end.camera_angle:
        if "side" in end.camera_angle or "45" in end.view_type:
            return "orbit_right"
        if "top" in end.camera_angle or "overhead" in end.view_type:
            return "tilt_down"

    # Default to smooth
    return "smooth"


async def link_transition_images(state: UGCPipelineState) -> UGCPipelineState:
    """
    After perspectives are generated, link the image URLs to transitions.

    This is called after perspective rendering to populate start/end image URLs.
    """
    if state.error:
        return state

    # Build lookup of perspective_id -> generated image URL
    perspective_urls = {}
    for gen_persp in state.generated_perspectives:
        if gen_persp.status == AssetStatus.SUCCESS and gen_persp.generated_url:
            perspective_urls[gen_persp.perspective_id] = gen_persp.generated_url

    # Link URLs to transitions
    for gen_trans in state.generated_transitions:
        # Find the transition definition
        trans = next(
            (t for t in state.transitions if t.transition_id == gen_trans.transition_id),
            None
        )
        if not trans:
            continue

        start_url = perspective_urls.get(trans.start_perspective_id)
        end_url = perspective_urls.get(trans.end_perspective_id)

        if start_url and end_url:
            gen_trans.start_image_url = start_url
            gen_trans.end_image_url = end_url
        else:
            gen_trans.status = AssetStatus.FAILED
            gen_trans.error_message = f"Missing images: start={bool(start_url)}, end={bool(end_url)}"

    return state
