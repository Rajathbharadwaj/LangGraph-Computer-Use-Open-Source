"""
Intake Agent - Normalizes raw product/business input into structured profile.

Stage 1 of the UGC pipeline.
"""

import json
from datetime import datetime
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..state import UGCPipelineState, ProductProfile
from ..config import settings
from .utils import load_template


INTAKE_SYSTEM_PROMPT = """You are a product/business analyst for a UGC ad factory.

Your job is to analyze the raw product or business information and extract a structured profile
that will be used to generate creative video ads.

You must extract and infer:
1. Key benefits - what does this product/business offer?
2. Pain points - what problems does it solve for customers?
3. Unique selling points - what makes it stand out?
4. Target audience - who is this for?
5. Tone - what's the appropriate brand voice?
6. Visual style hints - what aesthetics fit this brand?

Be thorough but concise. If information is missing, make reasonable inferences based on
the product category and typical customer expectations.

Respond with a JSON object matching this structure:
{
    "name": "string",
    "category": "string",
    "description": "string (1-2 sentences)",
    "target_audience": "string (describe the ideal customer)",
    "key_benefits": ["benefit1", "benefit2", ...],
    "pain_points": ["pain1", "pain2", ...],
    "unique_selling_points": ["usp1", "usp2", ...],
    "tone": "professional|playful|urgent|luxurious|friendly|bold",
    "price_point": "budget|mid-range|premium|luxury|null",
    "brand_colors": ["#hex1", "#hex2"] or [],
    "brand_guidelines": null or {"key": "value"}
}
"""


async def intake_product(state: UGCPipelineState) -> UGCPipelineState:
    """
    Stage 1: Normalize raw product input into structured ProductProfile.

    Takes raw input (name, description, images, etc.) and uses LLM to extract
    a comprehensive product profile for downstream creative generation.
    """
    state.current_stage = "intake"
    state.started_at = datetime.utcnow()

    # Get raw input
    raw_input = state.raw_input
    if not raw_input:
        state.error = "No raw input provided"
        return state

    # Build prompt with raw input
    user_prompt = f"""Analyze this product/business and create a structured profile:

Product Name: {raw_input.get('product_name', 'Unknown')}

Description:
{raw_input.get('product_description', 'No description provided')}

Target Audience (if specified): {raw_input.get('target_audience', 'Not specified')}

Key Benefits (if specified): {raw_input.get('key_benefits', [])}

Brand Colors (if specified): {raw_input.get('brand_colors', [])}

Reference Images: {len(raw_input.get('product_images', []))} images provided

Mode: {state.mode}

Create a comprehensive product profile for generating UGC video ads."""

    try:
        # Call LLM
        llm = ChatAnthropic(
            model=settings.llm_model,
            api_key=settings.anthropic_api_key,
            max_tokens=2000,
        )

        messages = [
            SystemMessage(content=INTAKE_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = await llm.ainvoke(messages)

        # Parse JSON response
        content = response.content
        # Handle markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        profile_data = json.loads(content.strip())

        # Add reference images from input
        profile_data["reference_images"] = raw_input.get("product_images", [])

        # Create ProductProfile
        state.product_profile = ProductProfile(**profile_data)

        # Log success
        state.warnings.append(
            f"Intake complete: {state.product_profile.name} ({state.product_profile.category})"
        )

    except json.JSONDecodeError as e:
        state.error = f"Failed to parse LLM response as JSON: {str(e)}"
    except Exception as e:
        state.error = f"Intake failed: {str(e)}"

    return state
