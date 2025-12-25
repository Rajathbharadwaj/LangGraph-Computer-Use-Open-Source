"""
CRM Service API Routes

FastAPI routes for:
- OAuth (connect messaging platforms)
- Customers (CRUD, tagging, visits)
- Conversations (unified inbox)
- Messages (send, draft)
- Webhooks (receive messages from Meta)
- Attribution (reports, customer journey)
"""

import logging
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request, Response, Query, Depends

from .config import get_crm_settings
from .models import (
    # Customers
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    CustomerListResponse,
    CustomerSearchParams,
    CustomerTagRequest,
    CustomerTagResponse,
    LifecycleStage,
    Channel,
    # Conversations
    ConversationResponse,
    ConversationListResponse,
    ConversationUpdateRequest,
    ConversationStatus,
    # Messages
    MessageResponse,
    MessageThreadResponse,
    SendMessageRequest,
    DraftReplyRequest,
    DraftReplyResponse,
    # Visits
    RecordVisitRequest,
    VisitResponse,
    # Events
    RecordEventRequest,
    ConversionEventResponse,
    # Followups
    CreateFollowupRequest,
    FollowupResponse,
    FollowupListResponse,
    FollowupType,
    # Attribution
    AttributionReportResponse,
    CustomerJourneyResponse,
    # Platform
    MessagingPlatformResponse,
    CheckinQRResponse,
    # Webhook
    WebhookEventResponse,
    # Error
    CRMErrorResponse,
)

logger = logging.getLogger(__name__)

# Create router
crm_router = APIRouter(prefix="/api/crm", tags=["CRM"])


# =============================================================================
# Dependency for getting user ID from headers
# =============================================================================


def get_user_id(request: Request) -> str:
    """Extract user ID from request headers."""
    user_id = request.headers.get("x-user-id") or request.headers.get("x-clerk-user-id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID required")
    return user_id


# =============================================================================
# OAuth Routes
# =============================================================================


@crm_router.get("/oauth/meta/url")
async def get_meta_oauth_url(request: Request, user_id: str = Depends(get_user_id)):
    """Get Meta OAuth URL for connecting messaging platforms."""
    from .services.oauth_manager import get_crm_oauth_manager

    oauth = get_crm_oauth_manager()
    url, state = await oauth.get_meta_messaging_oauth_url(user_id)

    return {"url": url, "state": state}


@crm_router.get("/oauth/meta/callback")
async def handle_meta_callback(
    code: str,
    state: str,
    request: Request,
):
    """Handle Meta OAuth callback."""
    from .services.oauth_manager import get_crm_oauth_manager
    from database.database import SessionLocal
    from database.models import MessagingPlatform, MessagingCredential
    from ads_service.routes import TokenEncryptionService
    import secrets

    oauth = get_crm_oauth_manager()

    try:
        user_id, platform_data = await oauth.handle_meta_messaging_callback(code, state)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Save platform and credentials
    db = SessionLocal()
    encryption = TokenEncryptionService()

    try:
        # Create or update platform
        platform = (
            db.query(MessagingPlatform)
            .filter(MessagingPlatform.user_id == user_id)
            .first()
        )

        if not platform:
            platform = MessagingPlatform(
                user_id=user_id,
                is_connected=True,
                checkin_code=secrets.token_urlsafe(8).lower(),
                webhook_verify_token=secrets.token_urlsafe(32),
            )
            db.add(platform)

        # Update with connected accounts
        whatsapp = platform_data.get("whatsapp", {})
        if whatsapp.get("accounts"):
            waba = whatsapp["accounts"][0]
            platform.waba_id = waba.get("waba_id")
            if waba.get("phone_numbers"):
                phone = waba["phone_numbers"][0]
                platform.phone_number_id = phone.get("id")
                platform.phone_number = phone.get("display_phone_number")

        instagram = platform_data.get("instagram", {})
        if instagram.get("accounts"):
            ig = instagram["accounts"][0]
            platform.instagram_account_id = ig.get("instagram_id")
            platform.instagram_username = ig.get("username")

        pages = platform_data.get("pages", {})
        if pages.get("pages"):
            page = pages["pages"][0]
            platform.page_id = page.get("page_id")
            platform.page_name = page.get("name")

        platform.is_connected = True
        db.flush()

        # Save credentials
        credential = (
            db.query(MessagingCredential)
            .filter(MessagingCredential.platform_id == platform.id)
            .first()
        )

        if not credential:
            credential = MessagingCredential(platform_id=platform.id)
            db.add(credential)

        credential.encrypted_access_token = encryption.encrypt_token(
            platform_data["access_token"]
        )

        db.commit()

        logger.info(f"Connected messaging platform for user {user_id}")

        # Return success page or redirect
        return Response(
            content="<html><body><h1>Connected!</h1><p>You can close this window.</p></body></html>",
            media_type="text/html",
        )

    except Exception as e:
        logger.error(f"Error saving platform: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        db.close()


# =============================================================================
# Customer Routes
# =============================================================================


@crm_router.get("/customers", response_model=CustomerListResponse)
async def list_customers(
    user_id: str = Depends(get_user_id),
    query: Optional[str] = None,
    lifecycle_stage: Optional[LifecycleStage] = None,
    tag: Optional[str] = None,
    source_channel: Optional[Channel] = None,
    has_visited: Optional[bool] = None,
    page: int = 1,
    page_size: int = 50,
):
    """List customers with optional filters."""
    from .services.customer_service import get_customer_service

    service = get_customer_service()

    params = CustomerSearchParams(
        query=query,
        lifecycle_stage=lifecycle_stage,
        tag=tag,
        source_channel=source_channel,
        has_visited=has_visited,
        page=page,
        page_size=page_size,
    )

    return service.search_customers(user_id, params)


@crm_router.get("/customers/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: int,
    user_id: str = Depends(get_user_id),
):
    """Get a customer by ID."""
    from .services.customer_service import get_customer_service

    service = get_customer_service()
    result = service.get_customer(user_id, customer_id)

    if not result:
        raise HTTPException(status_code=404, detail="Customer not found")

    return result


@crm_router.patch("/customers/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: int,
    data: CustomerUpdate,
    user_id: str = Depends(get_user_id),
):
    """Update a customer."""
    from .services.customer_service import get_customer_service

    service = get_customer_service()
    result = service.update_customer(user_id, customer_id, data)

    if not result:
        raise HTTPException(status_code=404, detail="Customer not found")

    return result


@crm_router.post("/customers/{customer_id}/tags", response_model=CustomerTagResponse)
async def add_customer_tag(
    customer_id: int,
    tag: CustomerTagRequest,
    user_id: str = Depends(get_user_id),
):
    """Add a tag to a customer."""
    from .services.customer_service import get_customer_service

    service = get_customer_service()
    result = service.add_tag(user_id, customer_id, tag)

    if not result:
        raise HTTPException(status_code=404, detail="Customer not found")

    return result


@crm_router.delete("/customers/{customer_id}/tags/{tag_name}")
async def remove_customer_tag(
    customer_id: int,
    tag_name: str,
    user_id: str = Depends(get_user_id),
):
    """Remove a tag from a customer."""
    from .services.customer_service import get_customer_service

    service = get_customer_service()
    success = service.remove_tag(user_id, customer_id, tag_name)

    if not success:
        raise HTTPException(status_code=404, detail="Tag not found")

    return {"success": True}


@crm_router.post("/customers/{customer_id}/visit", response_model=VisitResponse)
async def record_visit(
    customer_id: int,
    data: RecordVisitRequest,
    user_id: str = Depends(get_user_id),
):
    """Record a customer visit."""
    from .services.customer_service import get_customer_service

    service = get_customer_service()
    result = service.record_visit(user_id, customer_id, data.spent_cents or 0)

    if not result:
        raise HTTPException(status_code=404, detail="Customer not found")

    return result


# =============================================================================
# Conversation Routes (Unified Inbox)
# =============================================================================


@crm_router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    user_id: str = Depends(get_user_id),
    status: Optional[ConversationStatus] = None,
    channel: Optional[Channel] = None,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
):
    """Get unified inbox - all conversations."""
    from .services.conversation_service import get_conversation_service

    service = get_conversation_service()
    return service.get_inbox(
        user_id=user_id,
        status=status,
        channel=channel,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )


@crm_router.get("/conversations/{conversation_id}", response_model=MessageThreadResponse)
async def get_conversation(
    conversation_id: int,
    user_id: str = Depends(get_user_id),
):
    """Get a conversation with messages."""
    from .services.conversation_service import get_conversation_service

    service = get_conversation_service()
    result = service.get_messages(user_id, conversation_id)

    if not result:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return result


@crm_router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: int,
    data: ConversationUpdateRequest,
    user_id: str = Depends(get_user_id),
):
    """Update conversation status or read state."""
    from .services.conversation_service import get_conversation_service

    service = get_conversation_service()
    result = service.update_conversation(user_id, conversation_id, data)

    if not result:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return result


@crm_router.post("/conversations/{conversation_id}/messages", response_model=MessageResponse)
async def send_message(
    conversation_id: int,
    data: SendMessageRequest,
    user_id: str = Depends(get_user_id),
):
    """Send a message in a conversation."""
    from .services.conversation_service import get_conversation_service

    service = get_conversation_service()

    try:
        result = await service.send_message(user_id, conversation_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not result:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return result


@crm_router.post("/conversations/{conversation_id}/draft", response_model=DraftReplyResponse)
async def generate_draft(
    conversation_id: int,
    data: DraftReplyRequest,
    user_id: str = Depends(get_user_id),
):
    """Generate an AI draft reply."""
    from .services.conversation_service import get_conversation_service

    service = get_conversation_service()
    result = await service.generate_draft_reply(user_id, conversation_id, data)

    if not result:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return result


# =============================================================================
# Webhook Routes
# =============================================================================


@crm_router.get("/webhooks/meta")
async def verify_webhook(
    request: Request,
):
    """Meta webhook verification endpoint."""
    params = request.query_params
    mode = params.get("hub.mode")
    challenge = params.get("hub.challenge")
    verify_token = params.get("hub.verify_token")

    settings = get_crm_settings()

    if mode == "subscribe" and verify_token == settings.meta_webhook_verify_token:
        logger.info("Webhook verified successfully")
        return Response(content=challenge, media_type="text/plain")

    raise HTTPException(status_code=403, detail="Verification failed")


@crm_router.post("/webhooks/meta")
async def receive_webhook(request: Request):
    """Receive webhook events from Meta (WhatsApp, Instagram, Messenger)."""
    from .webhooks.meta_webhook import get_webhook_handler

    # Get raw body for signature verification
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    handler = get_webhook_handler()

    # Verify signature
    if not handler.verify_signature(body, signature):
        logger.warning("Invalid webhook signature")
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Parse payload
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Determine user from webhook (we need to look up platform)
    # This is simplified - in production, parse the webhook to get phone_number_id
    # and look up the user from MessagingPlatform
    user_id = None  # Will be determined by handler based on platform

    # Process webhook
    results = await handler.handle_webhook(payload, user_id)

    # Return 200 quickly (Meta expects fast response)
    return {"success": True, "processed": len(results)}


# =============================================================================
# Attribution Routes
# =============================================================================


@crm_router.get("/analytics/attribution", response_model=AttributionReportResponse)
async def get_attribution_report(
    user_id: str = Depends(get_user_id),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
):
    """Get attribution report linking campaigns to customer outcomes."""
    from .services.attribution_service import get_attribution_service

    service = get_attribution_service()
    return service.get_attribution_report(user_id, start_date, end_date)


@crm_router.get("/customers/{customer_id}/journey", response_model=CustomerJourneyResponse)
async def get_customer_journey(
    customer_id: int,
    user_id: str = Depends(get_user_id),
):
    """Get complete customer journey from ad click to purchase."""
    from .services.attribution_service import get_attribution_service

    service = get_attribution_service()
    result = service.get_customer_journey(user_id, customer_id)

    if not result:
        raise HTTPException(status_code=404, detail="Customer not found")

    return result


# =============================================================================
# Follow-up Routes
# =============================================================================


@crm_router.get("/followups", response_model=FollowupListResponse)
async def list_followups(
    user_id: str = Depends(get_user_id),
    limit: int = 50,
):
    """List pending follow-ups."""
    from .services.followup_scheduler import get_followup_scheduler

    scheduler = get_followup_scheduler()
    return scheduler.get_pending_followups(user_id, limit)


@crm_router.post("/customers/{customer_id}/followups", response_model=FollowupResponse)
async def schedule_followup(
    customer_id: int,
    data: CreateFollowupRequest,
    user_id: str = Depends(get_user_id),
):
    """Schedule a follow-up for a customer."""
    from .services.followup_scheduler import get_followup_scheduler

    scheduler = get_followup_scheduler()

    result_time = scheduler.schedule_followup(
        customer_id=customer_id,
        followup_type=data.followup_type,
        scheduled_at=data.scheduled_at,
        template_name=data.template_name,
    )

    if not result_time:
        raise HTTPException(status_code=400, detail="Failed to schedule follow-up")

    from database.database import SessionLocal
    from database.models import AutomatedFollowup

    db = SessionLocal()
    try:
        followup = (
            db.query(AutomatedFollowup)
            .filter(
                AutomatedFollowup.customer_id == customer_id,
                AutomatedFollowup.scheduled_at == result_time,
            )
            .first()
        )

        return FollowupResponse(
            id=followup.id,
            customer_id=followup.customer_id,
            followup_type=FollowupType(followup.followup_type),
            scheduled_at=followup.scheduled_at,
            status=followup.status,
            template_name=followup.template_name,
            created_at=followup.created_at,
        )
    finally:
        db.close()


@crm_router.delete("/followups/{followup_id}")
async def cancel_followup(
    followup_id: int,
    user_id: str = Depends(get_user_id),
):
    """Cancel a scheduled follow-up."""
    from .services.followup_scheduler import get_followup_scheduler

    scheduler = get_followup_scheduler()
    success = scheduler.cancel_followup(followup_id)

    if not success:
        raise HTTPException(status_code=404, detail="Follow-up not found")

    return {"success": True}


# =============================================================================
# Platform Routes
# =============================================================================


@crm_router.get("/platform", response_model=MessagingPlatformResponse)
async def get_platform(user_id: str = Depends(get_user_id)):
    """Get connected messaging platform info."""
    from database.database import SessionLocal
    from database.models import MessagingPlatform

    db = SessionLocal()
    try:
        platform = (
            db.query(MessagingPlatform)
            .filter(MessagingPlatform.user_id == user_id)
            .first()
        )

        if not platform:
            raise HTTPException(status_code=404, detail="No platform connected")

        return MessagingPlatformResponse(
            id=platform.id,
            waba_id=platform.waba_id,
            phone_number_id=platform.phone_number_id,
            phone_number=platform.phone_number,
            instagram_account_id=platform.instagram_account_id,
            instagram_username=platform.instagram_username,
            page_id=platform.page_id,
            page_name=platform.page_name,
            checkin_code=platform.checkin_code,
            is_connected=platform.is_connected,
            created_at=platform.created_at,
        )
    finally:
        db.close()


@crm_router.get("/platform/checkin-qr", response_model=CheckinQRResponse)
async def get_checkin_qr(user_id: str = Depends(get_user_id)):
    """Get QR code info for customer check-in."""
    from database.database import SessionLocal
    from database.models import MessagingPlatform

    db = SessionLocal()
    try:
        platform = (
            db.query(MessagingPlatform)
            .filter(MessagingPlatform.user_id == user_id)
            .first()
        )

        if not platform:
            raise HTTPException(status_code=404, detail="No platform connected")

        if not platform.phone_number:
            raise HTTPException(status_code=400, detail="No WhatsApp phone number configured")

        settings = get_crm_settings()

        # Build wa.me link with pre-filled message
        phone = platform.phone_number.lstrip("+")
        checkin_message = f"{settings.checkin_message_prefix}{platform.checkin_code}"
        whatsapp_link = f"https://wa.me/{phone}?text={checkin_message}"

        return CheckinQRResponse(
            checkin_code=platform.checkin_code,
            whatsapp_link=whatsapp_link,
            # QR image would be generated by frontend or a QR service
        )
    finally:
        db.close()
