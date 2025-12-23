"""
Atomic subagents for CRM Deep Agent.

Each subagent executes ONE atomic action:
- check_inbox: Get unread conversations
- draft_reply: Generate AI reply for approval
- send_message: Send an approved message
- tag_customer: Add/remove customer tags
- record_visit: Record visit and purchase
- schedule_followup: Schedule automated follow-up

Following the same pattern as ads_deep_agent.py subagents.
"""

from .prompts import (
    CHECK_INBOX_PROMPT,
    DRAFT_REPLY_PROMPT,
    SEND_MESSAGE_PROMPT,
    TAG_CUSTOMER_PROMPT,
    RECORD_VISIT_PROMPT,
    SCHEDULE_FOLLOWUP_PROMPT,
)
from .tools import (
    get_inbox_tool,
    get_conversation_tool,
    send_message_tool,
    generate_draft_tool,
    get_customer_tool,
    add_tag_tool,
    remove_tag_tool,
    record_visit_tool,
    schedule_followup_tool,
    get_customer_journey_tool,
)


def get_crm_subagents(store=None, user_id=None, model=None):
    """
    Get atomic subagents for CRM operations.

    Each subagent is a dict with:
    - name: Identifier for task() calls
    - description: What the subagent does (shown to main agent)
    - system_prompt: Instructions for the subagent
    - tools: List of tools the subagent can use

    Args:
        store: LangGraph Store (PostgresStore) for memory
        user_id: Clerk user ID
        model: LLM model instance

    Returns:
        List of subagent definitions
    """
    # Get current date for context
    from datetime import datetime
    import pytz

    pacific_tz = pytz.timezone("America/Los_Angeles")
    current_time = datetime.now(pacific_tz)
    date_context = f"Current date: {current_time.strftime('%A, %B %d, %Y')}"

    # Read-only tools for context
    context_tools = [get_inbox_tool, get_conversation_tool, get_customer_tool]

    subagents = [
        # =====================================================================
        # INBOX MANAGEMENT
        # =====================================================================
        {
            "name": "check_inbox",
            "description": """Check the unified inbox for conversations.

Shows all conversations across WhatsApp, Instagram DM, and Messenger.
Can filter by unread, channel, or get all.

Input: Optional filters (unread_only, channel)
Output: List of conversations with previews and counts""",
            "system_prompt": CHECK_INBOX_PROMPT + f"\n\n{date_context}",
            "tools": [get_inbox_tool],
        },
        {
            "name": "view_conversation",
            "description": """View a specific conversation thread.

Shows all messages in a conversation and customer details.

Input: conversation_id
Output: Full message thread and customer info""",
            "system_prompt": """You are a conversation viewer.

Your ONLY job: Retrieve and display a conversation thread.

STEPS:
1. Call get_conversation_tool with conversation_id
2. Format the messages in a readable thread
3. Show customer details and context

Output format:
- Customer: [Name] ([phone/channel])
- [Channel] | [Lifecycle stage] | [Visit count] visits
- Thread: [messages with timestamps]"""
            + f"\n\n{date_context}",
            "tools": [get_conversation_tool, get_customer_tool],
        },
        # =====================================================================
        # MESSAGE DRAFTING & SENDING
        # =====================================================================
        {
            "name": "draft_reply",
            "description": """Generate an AI draft reply for a conversation.

Reads the conversation context and generates an on-brand reply.
Returns draft for user approval before sending.

Input: conversation_id, optional context
Output: Draft reply text for approval""",
            "system_prompt": DRAFT_REPLY_PROMPT + f"\n\n{date_context}",
            "tools": [get_conversation_tool, generate_draft_tool, get_customer_tool],
        },
        {
            "name": "send_message",
            "description": """Send a message to a conversation.

Sends via the appropriate channel (WhatsApp, Instagram, Messenger).
Handles 24-hour window and template fallback.

Input: conversation_id, message content
Output: Delivery confirmation""",
            "system_prompt": SEND_MESSAGE_PROMPT + f"\n\n{date_context}",
            "tools": [send_message_tool, get_conversation_tool],
        },
        # =====================================================================
        # CUSTOMER MANAGEMENT
        # =====================================================================
        {
            "name": "tag_customer",
            "description": """Add or remove tags from a customer.

Tags help categorize and segment customers.
Smart tags (new_customer, returning) are auto-applied.

Input: customer_id, tag_name, action (add/remove)
Output: Confirmation of tag change""",
            "system_prompt": TAG_CUSTOMER_PROMPT + f"\n\n{date_context}",
            "tools": [add_tag_tool, remove_tag_tool, get_customer_tool],
        },
        {
            "name": "record_visit",
            "description": """Record a customer visit and optional purchase.

Updates visit count, lifecycle stage, and triggers follow-ups.
Automatically schedules review request if applicable.

Input: customer_id, optional spent_cents
Output: Updated visit stats and scheduled follow-ups""",
            "system_prompt": RECORD_VISIT_PROMPT + f"\n\n{date_context}",
            "tools": [record_visit_tool, get_customer_tool],
        },
        {
            "name": "view_customer",
            "description": """View detailed customer information.

Shows profile, tags, lifecycle stage, visit history, and attribution.

Input: customer_id
Output: Complete customer profile""",
            "system_prompt": """You are a customer profile viewer.

Your ONLY job: Retrieve and display customer details.

STEPS:
1. Call get_customer_tool with customer_id
2. Format the results clearly
3. Highlight key info (lifecycle, visits, source)

Include:
- Name and contact info
- Lifecycle stage and visit count
- Total spent
- Source campaign if from ad
- Tags (both smart and manual)"""
            + f"\n\n{date_context}",
            "tools": [get_customer_tool, get_customer_journey_tool],
        },
        # =====================================================================
        # FOLLOW-UP SCHEDULING
        # =====================================================================
        {
            "name": "schedule_followup",
            "description": """Schedule an automated follow-up message.

Types: review_request, visit_reminder, dormant_reactivation

Input: customer_id, followup_type, optional timing
Output: Confirmation with scheduled time""",
            "system_prompt": SCHEDULE_FOLLOWUP_PROMPT + f"\n\n{date_context}",
            "tools": [schedule_followup_tool, get_customer_tool],
        },
        # =====================================================================
        # ATTRIBUTION & JOURNEY
        # =====================================================================
        {
            "name": "view_customer_journey",
            "description": """View the complete customer journey.

Shows timeline: ad click -> first message -> visits -> purchases

Input: customer_id
Output: Journey timeline with attribution""",
            "system_prompt": """You are a customer journey viewer.

Your ONLY job: Display the complete customer journey.

STEPS:
1. Call get_customer_journey_tool with customer_id
2. Format the journey as a timeline
3. Highlight attribution (which ad brought them)

Output format:
[Date] - [Event Type] - [Details]
- 2024-12-01 - Ad Click - "BOGO Pizza" campaign
- 2024-12-01 - First Message - WhatsApp: "Hi, do you have..."
- 2024-12-05 - Visit - Check-in at store
- 2024-12-05 - Purchase - $45.00"""
            + f"\n\n{date_context}",
            "tools": [get_customer_journey_tool],
        },
    ]

    return subagents


def get_subagent_names():
    """Get list of available subagent names for documentation."""
    return [
        "check_inbox",
        "view_conversation",
        "draft_reply",
        "send_message",
        "tag_customer",
        "record_visit",
        "view_customer",
        "schedule_followup",
        "view_customer_journey",
    ]
