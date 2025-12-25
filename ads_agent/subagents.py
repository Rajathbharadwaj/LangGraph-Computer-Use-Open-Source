"""
Atomic subagents for Ads Deep Agent.

Each subagent executes ONE atomic action:
- generate_creative: Generate headlines, descriptions, targeting
- create_meta_campaign: Create campaign on Meta (draft)
- create_google_campaign: Create campaign on Google (draft)
- publish_campaign: Push campaign to platform (PAUSED)
- activate_campaign: Make campaign ACTIVE (live)
- research_audience: Research optimal targeting

Following the same pattern as x_growth_deep_agent.py subagents.
"""

from .prompts import (
    GENERATE_CREATIVE_PROMPT,
    CREATE_META_CAMPAIGN_PROMPT,
    CREATE_GOOGLE_CAMPAIGN_PROMPT,
    PUBLISH_CAMPAIGN_PROMPT,
    ACTIVATE_CAMPAIGN_PROMPT,
    RESEARCH_AUDIENCE_PROMPT,
    GENERATE_AD_IMAGE_PROMPT,
    CHECK_BRAND_ASSETS_PROMPT,
    get_generate_creative_prompt,
)
from .tools import (
    create_meta_campaign_tool,
    create_google_campaign_tool,
    publish_campaign_tool,
    activate_campaign_tool,
    get_user_platforms_tool,
    get_user_campaigns_tool,
    get_user_assets_tool,
    generate_ad_image_tool,
)


def get_ads_atomic_subagents(store=None, user_id=None, model=None, is_pro_tier=False):
    """
    Get atomic subagents for ads operations.

    Each subagent is a dict with:
    - name: Identifier for task() calls
    - description: What the subagent does (shown to main agent)
    - system_prompt: Instructions for the subagent
    - tools: List of tools the subagent can use

    Args:
        store: LangGraph Store (PostgresStore) for memory
        user_id: Clerk user ID
        model: LLM model instance (for web search)
        is_pro_tier: Whether to generate multiple variants

    Returns:
        List of subagent definitions
    """
    # Determine variant count based on tier
    variant_count = 4 if is_pro_tier else 1

    # Get current date for context
    from datetime import datetime
    import pytz

    pacific_tz = pytz.timezone("America/Los_Angeles")
    current_time = datetime.now(pacific_tz)
    date_context = f"Current date: {current_time.strftime('%A, %B %d, %Y')}"

    # User data tools (read-only context)
    user_data_tools = [get_user_platforms_tool, get_user_campaigns_tool]

    subagents = [
        # =====================================================================
        # CREATIVE GENERATION (Pure LLM, no tools needed)
        # =====================================================================
        {
            "name": "generate_creative",
            "description": f"""Generate ad creative (headlines, descriptions, targeting suggestions).

Generates {variant_count} variant(s) based on user tier.

Input: Natural language description of the promotion (e.g., "BOGO pizza this weekend")
Output: Structured JSON with headline, description, call_to_action, targeting_suggestions

Use this BEFORE creating campaigns to generate the creative content.""",
            "system_prompt": get_generate_creative_prompt(variant_count)
            + f"\n\n{date_context}",
            "tools": [],  # Pure LLM generation - no tools needed
        },
        # =====================================================================
        # CAMPAIGN CREATION (Draft status)
        # =====================================================================
        {
            "name": "create_meta_campaign",
            "description": """Create a campaign on Meta (Facebook/Instagram) in DRAFT status.

Input: Campaign details including name, headline, description, destination_url, daily_budget_cents, targeting
Output: Database campaign_id (not yet published to Meta)

The campaign will NOT be live until publish_campaign and activate_campaign are called.""",
            "system_prompt": CREATE_META_CAMPAIGN_PROMPT + f"\n\n{date_context}",
            "tools": [create_meta_campaign_tool] + user_data_tools,
        },
        {
            "name": "create_google_campaign",
            "description": """Create a Performance Max campaign on Google in DRAFT status.

Input: Campaign details including name, headline, description, destination_url, daily_budget_cents, targeting
Output: Database campaign_id (not yet published to Google)

The campaign will NOT be live until publish_campaign and activate_campaign are called.""",
            "system_prompt": CREATE_GOOGLE_CAMPAIGN_PROMPT + f"\n\n{date_context}",
            "tools": [create_google_campaign_tool] + user_data_tools,
        },
        # =====================================================================
        # CAMPAIGN PUBLISHING
        # =====================================================================
        {
            "name": "publish_campaign",
            "description": """Push a draft campaign to the ad platform (Meta or Google).

Creates the campaign on the platform in PAUSED status.
The campaign will NOT spend money until activate_campaign is called.

Input: Database campaign_id
Output: External platform campaign_id, confirmation of PAUSED status""",
            "system_prompt": PUBLISH_CAMPAIGN_PROMPT + f"\n\n{date_context}",
            "tools": [publish_campaign_tool] + user_data_tools,
        },
        # =====================================================================
        # CAMPAIGN ACTIVATION
        # =====================================================================
        {
            "name": "activate_campaign",
            "description": """Activate a published campaign (change from PAUSED to ACTIVE).

CRITICAL: This makes the campaign LIVE and starts spending budget!
Only call this AFTER the user has explicitly approved.

Input: Database campaign_id
Output: Confirmation that campaign is now ACTIVE and live""",
            "system_prompt": ACTIVATE_CAMPAIGN_PROMPT + f"\n\n{date_context}",
            "tools": [activate_campaign_tool] + user_data_tools,
        },
        # =====================================================================
        # AUDIENCE RESEARCH
        # =====================================================================
        {
            "name": "research_audience",
            "description": """Research optimal targeting for a business/promotion.

Uses available context to suggest:
- Demographics (age, gender)
- Interests and behaviors
- Location strategy
- Timing recommendations

Input: Business type, location, promotion type
Output: Recommended targeting configuration""",
            "system_prompt": RESEARCH_AUDIENCE_PROMPT + f"\n\n{date_context}",
            "tools": user_data_tools,  # Can access existing campaigns/platforms for context
        },
        # =====================================================================
        # CAMPAIGN STATUS CHECK
        # =====================================================================
        {
            "name": "check_campaigns",
            "description": """Check the status of existing campaigns.

Use this to see what campaigns exist and their current status.

Input: Optional status filter (draft, active, paused, archived)
Output: List of campaigns with status, budget, and performance summary""",
            "system_prompt": """You are a campaign status checker.

Your ONLY job: Check and report on existing campaigns.

Steps:
1. Call get_user_campaigns_tool with optional status filter
2. Format the results clearly
3. Report campaign statuses

IMPORTANT: This is read-only - do NOT modify any campaigns."""
            + f"\n\n{date_context}",
            "tools": user_data_tools,
        },
        # =====================================================================
        # PLATFORM CONNECTION CHECK
        # =====================================================================
        {
            "name": "check_platforms",
            "description": """Check which ad platforms are connected.

Use this to verify Meta and/or Google are connected before creating campaigns.

Input: None
Output: List of connected platforms with account details""",
            "system_prompt": """You are a platform connection checker.

Your ONLY job: Check which ad platforms are connected.

Steps:
1. Call get_user_platforms_tool
2. Report which platforms are connected
3. Note if any required platforms are missing

IMPORTANT: If platforms are not connected, guide user to connect them first."""
            + f"\n\n{date_context}",
            "tools": user_data_tools,
        },
        # =====================================================================
        # IMAGE GENERATION
        # =====================================================================
        {
            "name": "generate_ad_image",
            "description": """Generate an AI-powered ad image using Nano Banana Pro.

Uses the user's brand assets (logo, product photos) as references
to create cohesive, branded ad images.

Input: Description of the image to generate, aspect ratio (1:1, 16:9, etc.)
Output: Generated image URL

Can also link the generated image to an existing campaign.

Example: "Create a professional ad image for a pizza BOGO promotion, use our logo and pizza photos"
""",
            "system_prompt": GENERATE_AD_IMAGE_PROMPT + f"\n\n{date_context}",
            "tools": [get_user_assets_tool, generate_ad_image_tool],
        },
        # =====================================================================
        # BRAND ASSETS CHECK
        # =====================================================================
        {
            "name": "check_assets",
            "description": """Check what brand assets the user has uploaded.

Returns info about logos, product photos, and other assets
that can be used for AI image generation.

Input: None (optionally filter by asset type: logo, product, background, other)
Output: List of available assets with names and types""",
            "system_prompt": CHECK_BRAND_ASSETS_PROMPT + f"\n\n{date_context}",
            "tools": [get_user_assets_tool],
        },
    ]

    return subagents


def get_subagent_names():
    """Get list of available subagent names for documentation."""
    return [
        "generate_creative",
        "create_meta_campaign",
        "create_google_campaign",
        "publish_campaign",
        "activate_campaign",
        "research_audience",
        "check_campaigns",
        "check_platforms",
        "generate_ad_image",
        "check_assets",
    ]
