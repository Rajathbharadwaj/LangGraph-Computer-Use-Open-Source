"""
Tools for CRM Deep Agent subagents.

These wrap the crm_service APIs for use by subagents.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from langchain_core.tools import tool

from crm_service.models import (
    Channel,
    ConversationStatus,
    MessageType,
    FollowupType,
    CustomerTagRequest,
    SendMessageRequest,
)

logger = logging.getLogger(__name__)


# =============================================================================
# INBOX TOOLS
# =============================================================================


@tool
def get_inbox_tool(
    user_id: str,
    unread_only: bool = False,
    channel: Optional[str] = None,
    limit: int = 20,
) -> dict:
    """
    Get conversations from the unified inbox.

    Args:
        user_id: The Clerk user ID
        unread_only: Only return unread conversations
        channel: Filter by channel (whatsapp, instagram, messenger)
        limit: Max conversations to return

    Returns:
        dict with conversations list and counts
    """
    from crm_service.services.conversation_service import get_conversation_service

    service = get_conversation_service()

    result = service.get_inbox(
        user_id=user_id,
        unread_only=unread_only,
        channel=Channel(channel) if channel else None,
        limit=limit,
    )

    return {
        "success": True,
        "conversations": [
            {
                "id": c.id,
                "customer_id": c.customer_id,
                "customer_name": c.customer_name,
                "channel": c.channel.value,
                "is_unread": c.is_unread,
                "last_message_preview": c.last_message_preview,
                "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
                "window_open": c.window_open,
            }
            for c in result.conversations
        ],
        "total": result.total,
        "unread_count": result.unread_count,
    }


@tool
def get_conversation_tool(user_id: str, conversation_id: int) -> dict:
    """
    Get a specific conversation with all messages.

    Args:
        user_id: The Clerk user ID
        conversation_id: The conversation ID

    Returns:
        dict with conversation details and message thread
    """
    from crm_service.services.conversation_service import get_conversation_service

    service = get_conversation_service()

    result = service.get_messages(user_id=user_id, conversation_id=conversation_id)

    if not result:
        return {"success": False, "error": "Conversation not found"}

    return {
        "success": True,
        "conversation": {
            "id": result.conversation.id,
            "customer_id": result.conversation.customer_id,
            "customer_name": result.conversation.customer_name,
            "channel": result.conversation.channel.value,
            "window_open": result.conversation.window_open,
        },
        "messages": [
            {
                "id": m.id,
                "direction": m.direction.value,
                "content": m.content,
                "message_type": m.message_type.value,
                "created_at": m.created_at.isoformat(),
            }
            for m in result.messages
        ],
        "total_messages": result.total_messages,
    }


# =============================================================================
# MESSAGE TOOLS
# =============================================================================


@tool
async def send_message_tool(
    user_id: str,
    conversation_id: int,
    content: str,
    message_type: str = "text",
    template_name: Optional[str] = None,
) -> dict:
    """
    Send a message in a conversation.

    Args:
        user_id: The Clerk user ID
        conversation_id: The conversation to send in
        content: Message content
        message_type: Type (text, image, template)
        template_name: WhatsApp template name if outside 24hr window

    Returns:
        dict with message details and status
    """
    from crm_service.services.conversation_service import get_conversation_service

    service = get_conversation_service()

    request = SendMessageRequest(
        content=content,
        message_type=MessageType(message_type),
        template_name=template_name,
    )

    try:
        result = await service.send_message(
            user_id=user_id,
            conversation_id=conversation_id,
            data=request,
        )

        if not result:
            return {"success": False, "error": "Failed to send message"}

        return {
            "success": True,
            "message_id": result.id,
            "status": result.status.value,
            "content": result.content,
        }

    except ValueError as e:
        return {"success": False, "error": str(e)}


@tool
async def generate_draft_tool(
    user_id: str,
    conversation_id: int,
    context: Optional[str] = None,
) -> dict:
    """
    Generate an AI draft reply for a conversation.

    Args:
        user_id: The Clerk user ID
        conversation_id: The conversation to draft for
        context: Additional context for the AI

    Returns:
        dict with draft content for approval
    """
    from crm_service.services.conversation_service import get_conversation_service
    from crm_service.models import DraftReplyRequest

    service = get_conversation_service()

    request = DraftReplyRequest(context=context)

    try:
        result = await service.generate_draft_reply(
            user_id=user_id,
            conversation_id=conversation_id,
            request=request,
        )

        if not result:
            return {"success": False, "error": "Failed to generate draft"}

        return {
            "success": True,
            "draft_id": result.draft_id,
            "content": result.content,
            "suggested_followup": result.suggested_followup,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# CUSTOMER TOOLS
# =============================================================================


@tool
def get_customer_tool(user_id: str, customer_id: int) -> dict:
    """
    Get customer details.

    Args:
        user_id: The Clerk user ID
        customer_id: The customer ID

    Returns:
        dict with customer details
    """
    from crm_service.services.customer_service import get_customer_service

    service = get_customer_service()
    result = service.get_customer(user_id=user_id, customer_id=customer_id)

    if not result:
        return {"success": False, "error": "Customer not found"}

    return {
        "success": True,
        "customer": {
            "id": result.id,
            "first_name": result.first_name,
            "last_name": result.last_name,
            "phone_number": result.phone_number,
            "email": result.email,
            "lifecycle_stage": result.lifecycle_stage.value,
            "visit_count": result.visit_count,
            "total_spent_cents": result.total_spent_cents,
            "source_channel": result.source_channel,
            "source_campaign_name": result.source_campaign_name,
            "tags": [t.name for t in result.tags],
        },
    }


@tool
def add_tag_tool(user_id: str, customer_id: int, tag_name: str, category: Optional[str] = None) -> dict:
    """
    Add a tag to a customer.

    Args:
        user_id: The Clerk user ID
        customer_id: The customer ID
        tag_name: Name of the tag
        category: Optional tag category

    Returns:
        dict with tag details
    """
    from crm_service.services.customer_service import get_customer_service

    service = get_customer_service()

    request = CustomerTagRequest(name=tag_name, category=category)
    result = service.add_tag(user_id=user_id, customer_id=customer_id, tag=request)

    if not result:
        return {"success": False, "error": "Failed to add tag"}

    return {
        "success": True,
        "tag": {
            "id": result.id,
            "name": result.name,
            "category": result.category,
            "is_smart_tag": result.is_smart_tag,
        },
    }


@tool
def remove_tag_tool(user_id: str, customer_id: int, tag_name: str) -> dict:
    """
    Remove a tag from a customer.

    Args:
        user_id: The Clerk user ID
        customer_id: The customer ID
        tag_name: Name of the tag to remove

    Returns:
        dict with success status
    """
    from crm_service.services.customer_service import get_customer_service

    service = get_customer_service()
    success = service.remove_tag(user_id=user_id, customer_id=customer_id, tag_name=tag_name)

    return {"success": success}


@tool
def record_visit_tool(user_id: str, customer_id: int, spent_cents: int = 0) -> dict:
    """
    Record a customer visit.

    Args:
        user_id: The Clerk user ID
        customer_id: The customer ID
        spent_cents: Amount spent in cents (e.g., 4500 = $45)

    Returns:
        dict with updated visit stats
    """
    from crm_service.services.customer_service import get_customer_service

    service = get_customer_service()

    result = service.record_visit(
        user_id=user_id,
        customer_id=customer_id,
        spent_cents=spent_cents,
    )

    if not result:
        return {"success": False, "error": "Failed to record visit"}

    return {
        "success": True,
        "customer_id": result.customer_id,
        "visit_count": result.visit_count,
        "total_spent_cents": result.total_spent_cents,
        "review_request_scheduled": result.review_request_scheduled,
        "review_scheduled_at": result.review_scheduled_at.isoformat() if result.review_scheduled_at else None,
    }


# =============================================================================
# FOLLOWUP TOOLS
# =============================================================================


@tool
def schedule_followup_tool(
    user_id: str,
    customer_id: int,
    followup_type: str,
    hours_from_now: int = 24,
    template_name: Optional[str] = None,
) -> dict:
    """
    Schedule an automated follow-up.

    Args:
        user_id: The Clerk user ID
        customer_id: The customer ID
        followup_type: Type (review_request, visit_reminder, dormant_reactivation)
        hours_from_now: Hours until follow-up (default 24)
        template_name: WhatsApp template to use

    Returns:
        dict with followup details
    """
    from crm_service.services.followup_scheduler import FollowupScheduler
    from database.database import SessionLocal

    db = SessionLocal()
    try:
        scheduler = FollowupScheduler(db)
        scheduled_at = datetime.utcnow() + timedelta(hours=hours_from_now)

        if followup_type == "review_request":
            result_time = scheduler.schedule_review_request(customer_id)
        else:
            result_time = scheduler.schedule_followup(
                customer_id=customer_id,
                followup_type=FollowupType(followup_type),
                scheduled_at=scheduled_at,
                template_name=template_name,
            )

        if not result_time:
            return {"success": False, "error": "Failed to schedule followup"}

        return {
            "success": True,
            "customer_id": customer_id,
            "followup_type": followup_type,
            "scheduled_at": result_time.isoformat(),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}

    finally:
        db.close()


# =============================================================================
# ATTRIBUTION TOOLS
# =============================================================================


@tool
def get_customer_journey_tool(user_id: str, customer_id: int) -> dict:
    """
    Get the complete journey for a customer.

    Shows: ad click -> message -> visit -> purchase timeline.

    Args:
        user_id: The Clerk user ID
        customer_id: The customer ID

    Returns:
        dict with customer journey events
    """
    from crm_service.services.attribution_service import get_attribution_service

    service = get_attribution_service()
    result = service.get_customer_journey(user_id=user_id, customer_id=customer_id)

    if not result:
        return {"success": False, "error": "Customer not found"}

    return {
        "success": True,
        "customer_id": result.customer_id,
        "customer_name": result.customer_name,
        "source_campaign": result.source_campaign,
        "lifecycle_stage": result.lifecycle_stage.value,
        "total_spent_cents": result.total_spent_cents,
        "visit_count": result.visit_count,
        "events": [
            {
                "event_type": e.event_type,
                "timestamp": e.timestamp.isoformat(),
                "channel": e.channel,
                "campaign_name": e.campaign_name,
                "value_cents": e.value_cents,
            }
            for e in result.events
        ],
    }
