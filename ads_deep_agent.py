"""
Ads Deep Agent - Natural Language Ad Campaign Creation

Main DeepAgent: Understands requests, orchestrates campaign creation
Subagents: Execute atomic actions (generate creative, create campaign, publish)

Architecture mirrors x_growth_deep_agent.py:
- Main agent NEVER creates campaigns directly
- Main agent only: parses intent, delegates to subagents, handles approval flow
- Each subagent executes ONE atomic action
- Subagents return immediately after action

Registered in langgraph.json as "ads_deep_agent"
"""

import os
from typing import Optional

# IMPORTANT: Apply deepagents patch BEFORE importing create_deep_agent
# This patches subagent invocation to forward runtime config
import deepagents_patch  # noqa: F401 - imported for side effects

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langchain.chat_models import init_chat_model
from langchain_core.tools import tool

# Import ads agent modules
from ads_agent.prompts import get_main_prompt_with_context, MAIN_AGENT_PROMPT
from ads_agent.memory import AdsUserMemory, BusinessPreferences
from ads_agent.subagents import get_ads_atomic_subagents
from ads_agent.tools import (
    get_user_platforms_tool,
    get_user_campaigns_tool,
    create_business_context_tool,
    create_connected_platforms_tool,
)


# =============================================================================
# STORE BACKEND PATCHES (same as x_growth_deep_agent.py)
# =============================================================================

# Patch StoreBackend to use x-user-id for namespace instead of assistant_id
_original_get_namespace = StoreBackend._get_namespace


def _custom_get_namespace(self):
    """Get namespace using x-user-id from config instead of assistant_id."""
    namespace_base = "ads_filesystem"

    # Try to get x-user-id from runtime config
    runtime_cfg = getattr(self.runtime, "config", None)
    if isinstance(runtime_cfg, dict):
        # Check configurable first
        user_id = runtime_cfg.get("configurable", {}).get("x-user-id")
        if user_id:
            print(f"[AdsAgent] Using namespace: ({user_id}, {namespace_base})")
            return (user_id, namespace_base)

        # Fallback to metadata
        user_id = runtime_cfg.get("metadata", {}).get("x-user-id")
        if user_id:
            print(f"[AdsAgent] Using namespace from metadata: ({user_id}, {namespace_base})")
            return (user_id, namespace_base)

    # If no x-user-id found, fall back to original behavior
    print(f"[AdsAgent] No x-user-id found, falling back to default namespace")
    return _original_get_namespace(self)


StoreBackend._get_namespace = _custom_get_namespace


# =============================================================================
# MAIN AGENT CREATION
# =============================================================================


def create_ads_agent(config: dict = None):
    """
    Create the Ads Deep Agent with user-specific business context.

    Registered in langgraph.json as "ads_deep_agent"

    Args:
        config: RunnableConfig dict with optional configurable parameters:
            - model_name: The LLM model to use (default: claude-sonnet-4-5-20250929)
            - user_id: Clerk user ID for personalized context
            - store: LangGraph Store (PostgresStore or InMemoryStore)
            - is_pro_tier: Enable multi-variant generation (default: False)

    Returns:
        DeepAgent configured for ad campaign creation
    """
    if config is None:
        config = {}

    # Extract parameters from config
    configurable = config.get("configurable", {})
    model_name = configurable.get("model_name", "claude-sonnet-4-5-20250929")
    user_id = configurable.get("user_id") or configurable.get("x-user-id")
    store = configurable.get("store")
    is_pro_tier = configurable.get("is_pro_tier", False)

    # Initialize the model
    model = init_chat_model(model_name)

    # Get current date/time for context
    from datetime import datetime
    import pytz

    pacific_tz = pytz.timezone("America/Los_Angeles")
    current_time = datetime.now(pacific_tz)
    date_time_context = f"""
CURRENT DATE & TIME:
- Date: {current_time.strftime('%A, %B %d, %Y')}
- Time: {current_time.strftime('%I:%M %p')} Pacific Time

Use this for:
- Creating timely campaign names ("December Weekend Sale")
- Appropriate seasonal messaging
"""

    # Build system prompt with context
    system_prompt = MAIN_AGENT_PROMPT + date_time_context

    # Load business context if user_id and store available
    business_context = None
    connected_platforms = []

    if user_id and store:
        try:
            # Initialize user memory for ads preferences
            ads_memory = AdsUserMemory(store, user_id)
            preferences = ads_memory.get_preferences()

            if preferences:
                business_context = {
                    "business_name": preferences.business_name,
                    "business_type": preferences.business_type,
                    "location": f"{preferences.location_city}, {preferences.location_state}",
                }

                system_prompt += f"""

BUSINESS CONTEXT (from long-term memory):
- Business Name: {preferences.business_name}
- Business Type: {preferences.business_type}
- Location: {preferences.location_city}, {preferences.location_state}
- Service Radius: {preferences.service_radius_miles} miles
- Default Daily Budget: ${preferences.default_daily_budget_cents / 100:.2f}
- Target Audience: {preferences.target_audience}
- Brand Voice: {preferences.brand_voice}
- Website: {preferences.website_url or 'Not set'}

Use these defaults when user doesn't specify otherwise.
"""
                print(f"[AdsAgent] Loaded business preferences for {preferences.business_name}")
        except Exception as e:
            print(f"[AdsAgent] Could not load business preferences: {e}")

        # Check connected platforms
        try:
            platforms_result = get_user_platforms_tool.invoke({"user_id": user_id})
            if platforms_result.get("success"):
                platforms = platforms_result.get("platforms", [])
                connected_platforms = [p["platform"] for p in platforms]

                if connected_platforms:
                    system_prompt += f"""

CONNECTED AD PLATFORMS:
{', '.join([p.title() for p in connected_platforms])}

Create campaigns only for connected platforms.
"""
                else:
                    system_prompt += """

NO AD PLATFORMS CONNECTED YET.
When user asks to create ads, guide them to connect Meta or Google Ads first:
- Meta: /ads/oauth/meta/start
- Google: /ads/oauth/google/start
"""
                print(f"[AdsAgent] Connected platforms: {connected_platforms}")
        except Exception as e:
            print(f"[AdsAgent] Could not check platforms: {e}")

    # Add tier information
    tier_name = "PRO" if is_pro_tier else "GROWTH"
    system_prompt += f"""

USER TIER: {tier_name}
"""
    if is_pro_tier:
        system_prompt += """- Generate 3-4 creative variants for selection
- Offer A/B testing options
- Advanced targeting suggestions
"""
    else:
        system_prompt += """- Generate single best creative option
- Optimize for simplicity and speed
- Standard targeting
"""

    # Get atomic subagents
    subagents = get_ads_atomic_subagents(store, user_id, model, is_pro_tier)

    # Main agent tools (read-only context tools)
    main_tools = [get_user_platforms_tool, get_user_campaigns_tool]
    if user_id:
        main_tools.append(create_connected_platforms_tool(user_id))
        print(f"[AdsAgent] Added context tools for user {user_id}")

    # Configure backend for persistent storage
    # /memories/* paths go to StoreBackend (persistent across threads)
    # Other paths go to StateBackend (ephemeral)
    def make_backend(runtime):
        print(f"[AdsAgent] Creating CompositeBackend")
        print(f"[AdsAgent] runtime.store available: {runtime.store is not None}")

        return CompositeBackend(
            default=StateBackend(runtime),
            routes={"/memories/": StoreBackend(runtime)},
        )

    # Create the main agent
    agent = create_deep_agent(
        model=model,
        system_prompt=system_prompt,
        tools=main_tools,
        subagents=subagents,
        backend=make_backend,
        store=store,
    )

    print(f"[AdsAgent] Created Ads Deep Agent")
    print(f"[AdsAgent] User ID: {user_id}")
    print(f"[AdsAgent] Pro Tier: {is_pro_tier}")
    print(f"[AdsAgent] Subagents: {[s['name'] for s in subagents]}")

    return agent


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    """
    Example of how to use the Ads Deep Agent locally.

    In production, this is invoked via LangGraph Platform:
    - POST /threads/{thread_id}/runs
    - With graph_id: "ads_deep_agent"
    """

    # Create agent with default config
    agent = create_ads_agent()

    # Example conversation
    print("\n" + "=" * 60)
    print("Ads Deep Agent - Interactive Mode")
    print("=" * 60)
    print("\nExample prompts:")
    print("  - Create an ad for buy one get one pizza this weekend")
    print("  - Set up a campaign for 20% off all services")
    print("  - What platforms do I have connected?")
    print("  - Show me my current campaigns")
    print("\nType 'quit' to exit")
    print("-" * 60)

    # Note: In actual usage, you would use agent.invoke() or stream
    # This is just a demonstration of the agent creation
