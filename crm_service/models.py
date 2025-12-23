"""
Pydantic models for CRM Service API requests and responses.

Covers: Customers, Conversations, Messages, Tags, Events, Followups
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from enum import Enum


# =============================================================================
# Enums
# =============================================================================


class LifecycleStage(str, Enum):
    """Customer lifecycle stages."""
    LEAD = "lead"
    PROSPECT = "prospect"
    CUSTOMER = "customer"
    REPEAT = "repeat"
    CHURNED = "churned"


class Channel(str, Enum):
    """Messaging channels."""
    WHATSAPP = "whatsapp"
    INSTAGRAM = "instagram"
    MESSENGER = "messenger"


class ConversationStatus(str, Enum):
    """Conversation status."""
    OPEN = "open"
    SNOOZED = "snoozed"
    CLOSED = "closed"


class MessageDirection(str, Enum):
    """Message direction."""
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageType(str, Enum):
    """Message content type."""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    TEMPLATE = "template"
    CHECKIN = "checkin"
    INTERACTIVE = "interactive"


class MessageStatus(str, Enum):
    """Message delivery status."""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class FollowupType(str, Enum):
    """Automated followup types."""
    REVIEW_REQUEST = "review_request"
    VISIT_REMINDER = "visit_reminder"
    DORMANT_REACTIVATION = "dormant_reactivation"
    CUSTOM = "custom"


class FollowupStatus(str, Enum):
    """Followup status."""
    SCHEDULED = "scheduled"
    SENT = "sent"
    CANCELLED = "cancelled"
    FAILED = "failed"


class EventName(str, Enum):
    """Conversion event types for CAPI."""
    LEAD = "Lead"
    VISIT = "Visit"
    PURCHASE = "Purchase"
    ADD_TO_CART = "AddToCart"
    COMPLETE_REGISTRATION = "CompleteRegistration"


# =============================================================================
# Customer Models
# =============================================================================


class CustomerBase(BaseModel):
    """Base customer fields."""
    phone_number: Optional[str] = Field(None, description="E.164 format, e.g. +14155551234")
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class CustomerCreate(CustomerBase):
    """Create a new customer from inbound message."""
    source_channel: Channel
    instagram_id: Optional[str] = None
    messenger_id: Optional[str] = None
    whatsapp_id: Optional[str] = None
    ctwa_clid: Optional[str] = Field(None, description="Click-to-WhatsApp Click ID for attribution")
    source_campaign_id: Optional[int] = None


class CustomerUpdate(BaseModel):
    """Update customer fields."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    lifecycle_stage: Optional[LifecycleStage] = None


class CustomerTagRequest(BaseModel):
    """Add a tag to customer."""
    name: str = Field(..., max_length=50)
    category: Optional[str] = Field(None, max_length=50)


class CustomerTagResponse(BaseModel):
    """Customer tag response."""
    id: int
    name: str
    category: Optional[str] = None
    is_smart_tag: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class CustomerResponse(BaseModel):
    """Full customer response."""
    id: int
    phone_number: Optional[str] = None
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    profile_picture_url: Optional[str] = None

    # Attribution
    source_channel: Optional[str] = None
    source_campaign_id: Optional[int] = None
    source_campaign_name: Optional[str] = None

    # Lifecycle
    lifecycle_stage: LifecycleStage
    visit_count: int = 0
    last_visit_at: Optional[datetime] = None
    total_spent_cents: int = 0

    # Tags
    tags: List[CustomerTagResponse] = []

    # Timestamps
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CustomerListResponse(BaseModel):
    """Paginated customer list."""
    customers: List[CustomerResponse]
    total: int
    page: int = 1
    page_size: int = 50


class CustomerSearchParams(BaseModel):
    """Customer search/filter parameters."""
    query: Optional[str] = Field(None, description="Search by name, phone, email")
    lifecycle_stage: Optional[LifecycleStage] = None
    tag: Optional[str] = None
    source_channel: Optional[Channel] = None
    has_visited: Optional[bool] = None
    page: int = 1
    page_size: int = 50


# =============================================================================
# Conversation Models
# =============================================================================


class ConversationResponse(BaseModel):
    """Conversation in unified inbox."""
    id: int
    customer_id: int
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_profile_pic: Optional[str] = None

    channel: Channel
    status: ConversationStatus
    is_unread: bool = True

    # Last message preview
    last_message_preview: Optional[str] = None
    last_message_at: Optional[datetime] = None
    last_customer_message_at: Optional[datetime] = None

    # 24hr window for replies
    window_expires_at: Optional[datetime] = None
    window_open: bool = True

    # Attribution
    source_campaign_id: Optional[int] = None
    ctwa_clid: Optional[str] = None

    created_at: datetime

    class Config:
        from_attributes = True


class ConversationListResponse(BaseModel):
    """Unified inbox - list of conversations."""
    conversations: List[ConversationResponse]
    total: int
    unread_count: int


class ConversationUpdateRequest(BaseModel):
    """Update conversation status."""
    status: Optional[ConversationStatus] = None
    is_unread: Optional[bool] = None


# =============================================================================
# Message Models
# =============================================================================


class MessageBase(BaseModel):
    """Base message fields."""
    message_type: MessageType = MessageType.TEXT
    content: Optional[str] = None
    media_url: Optional[str] = None


class SendMessageRequest(MessageBase):
    """Request to send a message."""
    template_name: Optional[str] = Field(None, description="WhatsApp template name if outside 24hr window")
    template_params: Optional[List[str]] = None


class MessageResponse(BaseModel):
    """Message in conversation thread."""
    id: int
    conversation_id: int
    external_message_id: Optional[str] = None

    direction: MessageDirection
    message_type: MessageType
    content: Optional[str] = None
    media_url: Optional[str] = None

    # AI draft support
    is_ai_drafted: bool = False
    ai_draft_approved: bool = False

    # Delivery status
    status: MessageStatus
    error_message: Optional[str] = None

    # Timestamps
    created_at: datetime
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MessageThreadResponse(BaseModel):
    """Full conversation thread with messages."""
    conversation: ConversationResponse
    messages: List[MessageResponse]
    total_messages: int


class DraftReplyRequest(BaseModel):
    """Request AI to draft a reply."""
    context: Optional[str] = Field(None, description="Additional context for the AI")


class DraftReplyResponse(BaseModel):
    """AI-drafted reply for approval."""
    draft_id: int
    content: str
    suggested_followup: Optional[str] = None


# =============================================================================
# Conversion Event Models
# =============================================================================


class RecordEventRequest(BaseModel):
    """Record a conversion event."""
    event_name: EventName
    value_cents: Optional[int] = Field(0, ge=0, description="Purchase value in cents")
    event_source: str = "manual"
    campaign_id: Optional[int] = None


class ConversionEventResponse(BaseModel):
    """Conversion event record."""
    id: int
    customer_id: int
    event_name: str
    event_source: str
    value_cents: int

    # Attribution
    campaign_id: Optional[int] = None
    campaign_name: Optional[str] = None
    click_id: Optional[str] = None

    # CAPI sync status
    capi_synced_at: Optional[datetime] = None

    created_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# Automated Followup Models
# =============================================================================


class CreateFollowupRequest(BaseModel):
    """Schedule an automated followup."""
    followup_type: FollowupType
    scheduled_at: datetime
    template_name: Optional[str] = None
    custom_message: Optional[str] = None


class FollowupResponse(BaseModel):
    """Automated followup record."""
    id: int
    customer_id: int
    customer_name: Optional[str] = None
    followup_type: FollowupType
    scheduled_at: datetime
    status: FollowupStatus
    template_name: Optional[str] = None
    sent_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class FollowupListResponse(BaseModel):
    """List of scheduled followups."""
    followups: List[FollowupResponse]
    total: int


# =============================================================================
# Messaging Platform Models
# =============================================================================


class MessagingPlatformResponse(BaseModel):
    """Connected messaging platform."""
    id: int
    waba_id: Optional[str] = Field(None, description="WhatsApp Business Account ID")
    phone_number_id: Optional[str] = None
    phone_number: Optional[str] = None
    instagram_account_id: Optional[str] = None
    instagram_username: Optional[str] = None
    page_id: Optional[str] = None
    page_name: Optional[str] = None

    checkin_code: str = Field(..., description="Code for QR check-in, e.g. mario123")
    checkin_qr_url: Optional[str] = None

    is_connected: bool = True
    created_at: datetime

    class Config:
        from_attributes = True


class CheckinQRResponse(BaseModel):
    """QR code for customer check-in."""
    checkin_code: str
    whatsapp_link: str = Field(..., description="wa.me link with pre-filled message")
    qr_image_url: Optional[str] = None


# =============================================================================
# Attribution Report Models
# =============================================================================


class CampaignAttributionRow(BaseModel):
    """Attribution data for a single campaign."""
    campaign_id: int
    campaign_name: str
    platform: str

    # Ad metrics
    ad_spend_cents: int = 0
    impressions: int = 0
    clicks: int = 0

    # CRM outcomes
    leads: int = 0
    conversations: int = 0
    visits: int = 0
    purchases: int = 0
    revenue_cents: int = 0

    # Calculated
    cost_per_lead_cents: Optional[int] = None
    cost_per_visit_cents: Optional[int] = None
    roas: Optional[float] = None


class AttributionReportResponse(BaseModel):
    """Full attribution report linking ads to customer outcomes."""
    period_start: datetime
    period_end: datetime

    # Totals
    total_ad_spend_cents: int
    total_leads: int
    total_visits: int
    total_revenue_cents: int
    overall_roas: Optional[float] = None

    # Per-campaign breakdown
    campaigns: List[CampaignAttributionRow]


class CustomerJourneyEvent(BaseModel):
    """Single event in customer journey."""
    event_type: str  # ad_click, message, visit, purchase
    timestamp: datetime
    channel: Optional[str] = None
    campaign_name: Optional[str] = None
    content_preview: Optional[str] = None
    value_cents: Optional[int] = None


class CustomerJourneyResponse(BaseModel):
    """Full customer journey from ad click to purchase."""
    customer_id: int
    customer_name: Optional[str] = None
    phone_number: Optional[str] = None

    # Attribution
    source_campaign: Optional[str] = None
    source_channel: Optional[str] = None

    # Lifecycle
    lifecycle_stage: LifecycleStage
    total_spent_cents: int = 0
    visit_count: int = 0

    # Journey timeline
    events: List[CustomerJourneyEvent]


# =============================================================================
# Visit Tracking Models
# =============================================================================


class RecordVisitRequest(BaseModel):
    """Record a customer visit (from check-in or manual)."""
    spent_cents: Optional[int] = Field(0, ge=0, description="Amount spent during visit")
    notes: Optional[str] = None


class VisitResponse(BaseModel):
    """Visit confirmation."""
    customer_id: int
    visit_count: int
    total_spent_cents: int
    review_request_scheduled: bool = False
    review_scheduled_at: Optional[datetime] = None


# =============================================================================
# Webhook Models (for Meta webhook payload parsing)
# =============================================================================


class WebhookVerifyRequest(BaseModel):
    """Meta webhook verification challenge."""
    hub_mode: str = Field(..., alias="hub.mode")
    hub_challenge: str = Field(..., alias="hub.challenge")
    hub_verify_token: str = Field(..., alias="hub.verify_token")


class WhatsAppMessagePayload(BaseModel):
    """Parsed WhatsApp message from webhook."""
    from_number: str
    message_id: str
    timestamp: datetime
    message_type: MessageType
    text: Optional[str] = None
    media_url: Optional[str] = None
    context_message_id: Optional[str] = None
    # Click-to-WhatsApp attribution
    referral_ctwa_clid: Optional[str] = None
    referral_source_type: Optional[str] = None


class WebhookEventResponse(BaseModel):
    """Response after processing webhook event."""
    success: bool
    customer_id: Optional[int] = None
    conversation_id: Optional[int] = None
    message_id: Optional[int] = None
    is_checkin: bool = False
    is_new_customer: bool = False


# =============================================================================
# Error Models
# =============================================================================


class CRMErrorResponse(BaseModel):
    """Error response."""
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None
