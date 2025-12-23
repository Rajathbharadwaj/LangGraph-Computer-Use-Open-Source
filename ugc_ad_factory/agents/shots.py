"""
Shot Planner Agent - Breaks scripts into shot lists with visual directions.

Stage 4 of the UGC pipeline.
"""

import json
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..state import UGCPipelineState, ShotList, Shot
from ..config import settings
from .utils import load_template, generate_id


SHOTS_SYSTEM_PROMPT = """You are a video director for UGC short-form ads.

For each script, break it down into a shot list - the sequence of visual shots needed.

Each shot should have:
1. shot_type: hero_product, lifestyle, close_up, text_card, b_roll
2. duration_seconds: how long this shot lasts (typically 2-4 seconds)
3. description: what we see in this shot
4. camera_movement: static, pan_left, pan_right, zoom_in, zoom_out, ken_burns
5. subject: what's the focus (the product, a person, text, etc.)
6. background: description of the background
7. lighting: studio, natural, dramatic, soft, etc.

A typical 12-15 second video has 3-5 shots.

Shot type guidelines:
- hero_product: Clean product shot, centered, professional
- lifestyle: Product in use, real-world context
- close_up: Detail/texture shot, macro focus
- text_card: Bold text on solid/gradient background
- b_roll: Supplementary footage, transitions

Respond with a JSON array:
[
    {
        "shotlist_id": "shotlist_001",
        "script_id": "script_001",
        "angle_id": "angle_000",
        "shots": [
            {
                "shot_id": "shot_001_01",
                "shot_type": "text_card",
                "duration_seconds": 2.5,
                "description": "Bold hook text appears",
                "camera_movement": "static",
                "subject": "Hook text overlay",
                "background": "gradient purple to blue",
                "lighting": "n/a"
            },
            {
                "shot_id": "shot_001_02",
                "shot_type": "hero_product",
                "duration_seconds": 3.0,
                "description": "Product centered, slow zoom in",
                "camera_movement": "zoom_in",
                "subject": "Product bottle",
                "background": "clean white studio",
                "lighting": "soft studio"
            }
        ],
        "total_duration": 12.0,
        "transition_style": "cut"
    },
    ...
]
"""


async def plan_shots(state: UGCPipelineState) -> UGCPipelineState:
    """
    Stage 4: Break scripts into detailed shot lists.

    Creates a ShotList for each script with visual direction for each shot.
    """
    state.current_stage = "shots"

    if state.error:
        return state

    if not state.script_packages:
        state.error = "No scripts available (script writing stage failed?)"
        return state

    profile = state.product_profile

    # Try to load shot type templates
    try:
        shot_templates = load_template(state.mode, "shots")
        shot_types = shot_templates.get("shot_types", [])
    except ValueError:
        shot_types = []
        state.warnings.append(f"No shot templates for mode {state.mode}")

    # Build prompt with scripts
    scripts_json = json.dumps(
        [
            {
                "script_id": s.script_id,
                "angle_id": s.angle_id,
                "voiceover_text": s.voiceover_text,
                "text_overlays": s.text_overlays,
                "duration_seconds": s.duration_seconds,
            }
            for s in state.script_packages
        ],
        indent=2,
    )

    user_prompt = f"""Create shot lists for these {len(state.script_packages)} scripts:

Product: {profile.name}
Category: {profile.category}
Visual Style: {profile.tone}
Reference: {len(profile.reference_images)} product images available

{"Available shot types:" if shot_types else ""}
{json.dumps(shot_types, indent=2) if shot_types else ""}

Scripts to visualize:
{scripts_json}

Create a shot list for EACH script. Each shot list should have 3-5 shots that tell a visual story.
Ensure shots sync with the text overlay timings from the script."""

    try:
        llm = ChatAnthropic(
            model=settings.llm_model,
            api_key=settings.anthropic_api_key,
            max_tokens=16000,
        )

        messages = [
            SystemMessage(content=SHOTS_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = await llm.ainvoke(messages)

        # Parse JSON response
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        shotlists_data = json.loads(content.strip())

        # Create ShotList objects
        state.shot_lists = []
        for i, sl_data in enumerate(shotlists_data):
            # Create Shot objects
            shots = []
            for j, shot_data in enumerate(sl_data.get("shots", [])):
                shot = Shot(
                    shot_id=shot_data.get("shot_id", generate_id(f"shot_{i}", j)),
                    shot_type=shot_data.get("shot_type", "hero_product"),
                    duration_seconds=shot_data.get("duration_seconds", 3.0),
                    description=shot_data.get("description", ""),
                    camera_movement=shot_data.get("camera_movement", "static"),
                    subject=shot_data.get("subject", "product"),
                    background=shot_data.get("background", "clean studio"),
                    lighting=shot_data.get("lighting", "studio"),
                )
                shots.append(shot)

            shotlist = ShotList(
                shotlist_id=generate_id("shotlist", i),
                script_id=sl_data.get("script_id", state.script_packages[i].script_id if i < len(state.script_packages) else f"script_{i}"),
                angle_id=sl_data.get("angle_id", state.angles[i].angle_id if i < len(state.angles) else f"angle_{i}"),
                shots=shots,
                total_duration=sl_data.get("total_duration", sum(s.duration_seconds for s in shots)),
                transition_style=sl_data.get("transition_style", "cut"),
            )
            state.shot_lists.append(shotlist)

        state.warnings.append(
            f"Generated {len(state.shot_lists)} shot lists with {sum(len(sl.shots) for sl in state.shot_lists)} total shots"
        )

    except json.JSONDecodeError as e:
        state.error = f"Failed to parse shot lists response: {str(e)}"
    except Exception as e:
        state.error = f"Shot planning failed: {str(e)}"

    return state
