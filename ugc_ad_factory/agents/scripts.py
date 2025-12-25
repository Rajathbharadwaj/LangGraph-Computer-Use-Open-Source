"""
Script Writer Agent - Converts angles into voiceover scripts and text overlays.

Stage 3 of the UGC pipeline.
"""

import json
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..state import UGCPipelineState, ScriptPackage
from ..config import settings
from .utils import generate_id


SCRIPTS_SYSTEM_PROMPT = """You are a UGC script writer specializing in short-form video ads.

For each creative angle, write a complete script package including:
1. Voiceover text (optional, for voice-narrated ads)
2. Text overlays with timestamps (the on-screen text)
3. A clear CTA (call-to-action)
4. Music mood suggestion

Scripts should be 10-15 seconds when read aloud. Text overlays should be punchy and scannable.

Each text overlay should have:
- time: seconds from start (0.0, 2.5, 5.0, etc.)
- text: the overlay text (keep under 10 words per overlay)
- style: "hook" | "benefit" | "cta" | "social_proof"

Respond with a JSON array:
[
    {
        "script_id": "script_001",
        "angle_id": "angle_000",
        "voiceover_text": "Full voiceover script here or null if text-only",
        "text_overlays": [
            {"time": 0.0, "text": "POV: You're tired of...", "style": "hook"},
            {"time": 3.0, "text": "This changes everything", "style": "benefit"},
            {"time": 6.0, "text": "Link in bio", "style": "cta"}
        ],
        "cta_text": "Link in bio to grab yours",
        "duration_seconds": 12,
        "music_mood": "upbeat"
    },
    ...
]
"""


async def write_scripts(state: UGCPipelineState) -> UGCPipelineState:
    """
    Stage 3: Convert angles into scripts with voiceover and text overlays.

    Creates a ScriptPackage for each angle.
    """
    state.current_stage = "scripts"

    if state.error:
        return state

    if not state.angles:
        state.error = "No angles available (angle generation stage failed?)"
        return state

    profile = state.product_profile

    # Build prompt with all angles
    angles_json = json.dumps(
        [
            {
                "angle_id": a.angle_id,
                "name": a.name,
                "hook_type": a.hook_type,
                "hook_text": a.hook_text,
                "emotional_trigger": a.emotional_trigger,
                "target_segment": a.target_segment,
            }
            for a in state.angles
        ],
        indent=2,
    )

    user_prompt = f"""Write scripts for these {len(state.angles)} creative angles:

Product: {profile.name}
Description: {profile.description}
Key Benefits: {', '.join(profile.key_benefits[:3])}
Tone: {profile.tone}
CTA Style: "Link in bio" / "Shop now" / "Try it free"

Angles to script:
{angles_json}

Create a script package for EACH angle. Each video should be 10-15 seconds.
Text overlays should sync with the hook, benefits, and CTA timing."""

    try:
        llm = ChatAnthropic(
            model=settings.llm_model,
            api_key=settings.anthropic_api_key,
            max_tokens=16000,
        )

        messages = [
            SystemMessage(content=SCRIPTS_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = await llm.ainvoke(messages)

        # Parse JSON response
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        scripts_data = json.loads(content.strip())

        # Create ScriptPackage objects
        state.script_packages = []
        for i, script_data in enumerate(scripts_data):
            script = ScriptPackage(
                script_id=generate_id("script", i),
                angle_id=script_data.get("angle_id", state.angles[i].angle_id if i < len(state.angles) else f"angle_{i}"),
                voiceover_text=script_data.get("voiceover_text"),
                text_overlays=script_data.get("text_overlays", []),
                cta_text=script_data.get("cta_text", "Link in bio"),
                duration_seconds=script_data.get("duration_seconds", 15),
                music_mood=script_data.get("music_mood", "upbeat"),
            )
            state.script_packages.append(script)

        state.warnings.append(f"Generated {len(state.script_packages)} scripts")

    except json.JSONDecodeError as e:
        state.error = f"Failed to parse scripts response: {str(e)}"
    except Exception as e:
        state.error = f"Script writing failed: {str(e)}"

    return state
