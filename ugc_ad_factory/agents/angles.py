"""
Angle Generator Agent - Generates creative angles/hooks for video ads.

Stage 2 of the UGC pipeline.
"""

import json
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..state import UGCPipelineState, CreativeAngle
from ..config import settings
from .utils import load_template, generate_id


ANGLES_SYSTEM_PROMPT = """You are a creative director for a UGC ad factory.

Your job is to generate multiple creative "angles" - different hook strategies and emotional
approaches for video ads promoting the same product.

Each angle should have:
1. A unique hook type (problem_solution, social_proof, before_after, urgency, unboxing, testimonial, etc.)
2. A compelling hook text (the opening line that grabs attention)
3. An emotional trigger (the feeling you're targeting)
4. A target segment (who this angle appeals to most)

Generate diverse angles that can each become a separate 10-15 second video ad.
The angles should be distinct enough that they feel like different ads, not variations of the same ad.

Respond with a JSON array of angle objects:
[
    {
        "name": "The Problem Solver",
        "hook_type": "problem_solution",
        "hook_text": "Tired of [pain point]? Here's the fix...",
        "emotional_trigger": "frustration_to_relief",
        "target_segment": "busy professionals",
        "estimated_effectiveness": 0.85
    },
    ...
]
"""


async def generate_angles(state: UGCPipelineState) -> UGCPipelineState:
    """
    Stage 2: Generate creative angles from product profile.

    Creates 20-30 distinct creative angles that will each become a video ad.
    Uses mode-specific angle templates as a starting point.
    """
    state.current_stage = "angles"

    if state.error:
        return state

    if not state.product_profile:
        state.error = "No product profile available (intake stage failed?)"
        return state

    try:
        # Load angle templates for this mode
        angle_templates = load_template(state.mode, "angles")
        template_patterns = angle_templates.get("angle_patterns", [])
    except ValueError:
        # No template, will generate purely from LLM
        template_patterns = []
        state.warnings.append(f"No angle templates for mode {state.mode}, using LLM only")

    # Build prompt
    profile = state.product_profile
    target_count = state.target_count

    user_prompt = f"""Generate {target_count} creative angles for this product:

Product: {profile.name}
Category: {profile.category}
Description: {profile.description}
Target Audience: {profile.target_audience}
Key Benefits: {', '.join(profile.key_benefits)}
Pain Points: {', '.join(profile.pain_points)}
USPs: {', '.join(profile.unique_selling_points)}
Tone: {profile.tone}

{"Use these angle patterns as inspiration (but create variations):" if template_patterns else ""}
{json.dumps(template_patterns, indent=2) if template_patterns else ""}

Generate {target_count} distinct angles. Each should feel like a completely different ad approach.
Focus on short-form video (10-15 seconds) hooks that work on TikTok, Reels, and YouTube Shorts."""

    try:
        # Call LLM
        llm = ChatAnthropic(
            model=settings.llm_model,
            api_key=settings.anthropic_api_key,
            max_tokens=8000,
        )

        messages = [
            SystemMessage(content=ANGLES_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = await llm.ainvoke(messages)

        # Parse JSON response
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        angles_data = json.loads(content.strip())

        # Create CreativeAngle objects with IDs
        state.angles = []
        for i, angle_data in enumerate(angles_data):
            angle = CreativeAngle(
                angle_id=generate_id("angle", i),
                name=angle_data.get("name", f"Angle {i+1}"),
                hook_type=angle_data.get("hook_type", "general"),
                hook_text=angle_data.get("hook_text", ""),
                emotional_trigger=angle_data.get("emotional_trigger", "curiosity"),
                target_segment=angle_data.get("target_segment", "general"),
                estimated_effectiveness=angle_data.get("estimated_effectiveness", 0.8),
            )
            state.angles.append(angle)

        state.warnings.append(f"Generated {len(state.angles)} creative angles")

    except json.JSONDecodeError as e:
        state.error = f"Failed to parse angles response: {str(e)}"
    except Exception as e:
        state.error = f"Angle generation failed: {str(e)}"

    return state
