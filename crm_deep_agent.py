"""
CRM Deep Agent - Unified Inbox & Customer Relationship Management

Main DeepAgent: Manages customer conversations, drafts replies, tracks visits
Subagents: Execute atomic actions (draft reply, send message, tag customer, etc.)

Architecture mirrors ads_deep_agent.py:
- Main agent NEVER sends messages directly
- Main agent only: views inbox, orchestrates subagents, handles approval flow
- Each subagent executes ONE atomic action
- Subagents return immediately after action

Registered in langgraph.json as "crm_deep_agent"
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

# Import CRM agent modules
from crm_agent.prompts import get_main_prompt_with_context, MAIN_AGENT_PROMPT
from crm_agent.subagents import get_crm_subagents
from crm_agent.tools import get_inbox_tool, get_customer_tool


# =============================================================================
# STORE BACKEND PATCHES (same as ads_deep_agent.py)
# =============================================================================

# Patch StoreBackend to use x-user-id for namespace instead of assistant_id
_original_get_namespace = StoreBackend._get_namespace


def _custom_get_namespace(self):
    """Get namespace using x-user-id from config instead of assistant_id."""
    namespace_base = "crm_filesystem"

    # Try to get x-user-id from runtime config
    runtime_cfg = getattr(self.runtime, "config", None)
    if isinstance(runtime_cfg, dict):
        # Check configurable first
        user_id = runtime_cfg.get("configurable", {}).get("x-user-id")
        if user_id:
            print(f"[CRMAgent] Using namespace: ({user_id}, {namespace_base})")
            return (user_id, namespace_base)

        # Fallback to metadata
        user_id = runtime_cfg.get("metadata", {}).get("x-user-id")
        if user_id:
            print(f"[CRMAgent] Using namespace from metadata: ({user_id}, {namespace_base})")
            return (user_id, namespace_base)

    # If no x-user-id found, fall back to original behavior
    print(f"[CRMAgent] No x-user-id found, falling back to default namespace")
    return _original_get_namespace(self)


StoreBackend._get_namespace = _custom_get_namespace


# =============================================================================
# MAIN AGENT CREATION
# =============================================================================


def create_crm_agent(config: dict = None):
    """
    Create the CRM Deep Agent with user-specific context.

    Registered in langgraph.json as "crm_deep_agent"

    Args:
        config: RunnableConfig dict with optional configurable parameters:
            - model_name: The LLM model to use (default: claude-sonnet-4-5-20250929)
            - user_id: Clerk user ID for personalized context
            - store: LangGraph Store (PostgresStore or InMemoryStore)

    Returns:
        DeepAgent configured for CRM operations
    """
    if config is None:
        config = {}

    # Extract parameters from config
    configurable = config.get("configurable", {})
    model_name = configurable.get("model_name", "claude-sonnet-4-5-20250929")
    user_id = configurable.get("user_id") or configurable.get("x-user-id")
    store = configurable.get("store")

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
- Timely responses ("We're open until 9pm tonight!")
- Appropriate greetings (morning/afternoon/evening)
"""

    # Build system prompt with context
    system_prompt = MAIN_AGENT_PROMPT + date_time_context

    # Load business context if user_id is available
    business_context = None
    connected_channels = []
    unread_count = 0

    if user_id:
        try:
            # Check for connected messaging platform
            from database.database import SessionLocal
            from database.models import MessagingPlatform, Conversation

            db = SessionLocal()

            platform = (
                db.query(MessagingPlatform)
                .filter(
                    MessagingPlatform.user_id == user_id,
                    MessagingPlatform.is_connected == True,
                )
                .first()
            )

            if platform:
                channels = []
                if platform.phone_number_id:
                    channels.append("WhatsApp")
                if platform.instagram_account_id:
                    channels.append("Instagram")
                if platform.page_id:
                    channels.append("Messenger")
                connected_channels = channels

                system_prompt += f"""

CONNECTED CHANNELS:
{', '.join(channels)}

You can manage conversations from these platforms.
"""
                print(f"[CRMAgent] Connected channels: {channels}")

            else:
                system_prompt += """

NO MESSAGING CHANNELS CONNECTED YET.
When user asks about inbox/messages, guide them to connect:
- WhatsApp Business: Requires Meta Business Suite setup
- Instagram: Connect via Meta OAuth
- Messenger: Connect via Facebook Page
"""

            # Count unread conversations
            unread_count = (
                db.query(Conversation)
                .filter(
                    Conversation.user_id == user_id,
                    Conversation.is_unread == True,
                )
                .count()
            )

            if unread_count > 0:
                system_prompt += f"""

INBOX STATUS:
You have {unread_count} unread conversation(s).
"""
                print(f"[CRMAgent] Unread conversations: {unread_count}")

            db.close()

        except Exception as e:
            print(f"[CRMAgent] Could not load context: {e}")

        # Try to load business preferences from ads memory if available
        try:
            from ads_agent.memory import AdsUserMemory

            if store:
                ads_memory = AdsUserMemory(store, user_id)
                preferences = ads_memory.get_preferences()

                if preferences:
                    system_prompt += f"""

BUSINESS CONTEXT:
- Business Name: {preferences.business_name}
- Business Type: {preferences.business_type}
- Location: {preferences.location_city}, {preferences.location_state}
- Brand Voice: {preferences.brand_voice}

Match this brand voice in reply drafts.
"""
                    print(f"[CRMAgent] Loaded business context: {preferences.business_name}")

        except Exception as e:
            print(f"[CRMAgent] Could not load business preferences: {e}")

    # Get atomic subagents
    subagents = get_crm_subagents(store, user_id, model)

    # Main agent tools (read-only context tools)
    main_tools = [get_inbox_tool, get_customer_tool]

    # Configure backend for persistent storage
    def make_backend(runtime):
        print(f"[CRMAgent] Creating CompositeBackend")
        print(f"[CRMAgent] runtime.store available: {runtime.store is not None}")

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

    print(f"[CRMAgent] Created CRM Deep Agent")
    print(f"[CRMAgent] User ID: {user_id}")
    print(f"[CRMAgent] Connected Channels: {connected_channels}")
    print(f"[CRMAgent] Unread Conversations: {unread_count}")
    print(f"[CRMAgent] Subagents: {[s['name'] for s in subagents]}")

    return agent


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    """
    Example of how to use the CRM Deep Agent locally.

    In production, this is invoked via LangGraph Platform:
    - POST /threads/{thread_id}/runs
    - With graph_id: "crm_deep_agent"
    """

    # Create agent with default config
    agent = create_crm_agent()

    # Example conversation
    print("\n" + "=" * 60)
    print("CRM Deep Agent - Interactive Mode")
    print("=" * 60)
    print("\nExample prompts:")
    print("  - Check my inbox")
    print("  - Show me the conversation with John")
    print("  - Draft a reply to conversation 123")
    print("  - Record a visit for customer 456, they spent $45")
    print("  - Schedule a review request for Sarah in 24 hours")
    print("\nType 'quit' to exit")
    print("-" * 60)

    # Note: In actual usage, you would use agent.invoke() or stream
    # This is just a demonstration of the agent creation
