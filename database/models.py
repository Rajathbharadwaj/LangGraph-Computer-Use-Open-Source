"""
Database models for X Growth Automation
"""
from sqlalchemy import Column, String, Integer, DateTime, Date, Boolean, Text, ForeignKey, JSON, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class User(Base):
    """
    User account (authenticated via Clerk)
    """
    __tablename__ = "users"

    id = Column(String, primary_key=True)  # Clerk user ID
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Subscription info (legacy field for backwards compatibility)
    plan = Column(String, default="free")  # free, pro, pro_plus, ultimate
    is_active = Column(Boolean, default=True)

    # Stripe customer ID (created when user signs up or first subscribes)
    stripe_customer_id = Column(String(100), unique=True, nullable=True)

    # Relationships
    x_accounts = relationship("XAccount", back_populates="user", cascade="all, delete-orphan")
    api_usage = relationship("APIUsage", back_populates="user", cascade="all, delete-orphan")
    cron_jobs = relationship("CronJob", back_populates="user", cascade="all, delete-orphan")
    subscription = relationship("Subscription", back_populates="user", uselist=False, cascade="all, delete-orphan")


class XAccount(Base):
    """
    Connected X (Twitter) accounts
    """
    __tablename__ = "x_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # X account info
    username = Column(String, nullable=False)
    display_name = Column(String)
    profile_image_url = Column(String)

    # Status
    is_connected = Column(Boolean, default=True)
    last_synced_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Cookies stored directly as JSON for simpler access
    cookies = Column(JSON)

    # Relationships
    user = relationship("User", back_populates="x_accounts")
    encrypted_cookies = relationship("UserCookies", back_populates="x_account", cascade="all, delete-orphan")
    posts = relationship("UserPost", back_populates="x_account", cascade="all, delete-orphan")


class UserCookies(Base):
    """
    Encrypted X cookies for each account
    """
    __tablename__ = "user_cookies"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    x_account_id = Column(Integer, ForeignKey("x_accounts.id"), nullable=False)
    
    # Encrypted cookie data
    encrypted_cookies = Column(Text, nullable=False)
    
    # Metadata
    captured_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    
    # Relationships
    x_account = relationship("XAccount", back_populates="encrypted_cookies")


class UserPost(Base):
    """
    User's X posts for writing style learning
    """
    __tablename__ = "user_posts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    x_account_id = Column(Integer, ForeignKey("x_accounts.id"), nullable=False)
    
    # Post content
    content = Column(Text, nullable=False)
    post_url = Column(String)
    
    # Engagement metrics
    likes = Column(Integer, default=0)
    retweets = Column(Integer, default=0)
    replies = Column(Integer, default=0)
    
    # Metadata
    posted_at = Column(DateTime)
    imported_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    x_account = relationship("XAccount", back_populates="posts")


class APIUsage(Base):
    """
    Track API usage for rate limiting and billing
    """
    __tablename__ = "api_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Usage tracking
    endpoint = Column(String, nullable=False)
    request_count = Column(Integer, default=1)

    # Timestamps
    date = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="api_usage")


class ScheduledPost(Base):
    """
    Scheduled posts for content calendar
    """
    __tablename__ = "scheduled_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    x_account_id = Column(Integer, ForeignKey("x_accounts.id"), nullable=False)

    # Post content
    content = Column(Text, nullable=False)
    media_urls = Column(JSON, default=[])  # Array of S3/Cloudinary URLs

    # Status
    status = Column(String, nullable=False, default="draft")  # draft, scheduled, posted, failed

    # Scheduling
    scheduled_at = Column(DateTime)  # When to post
    posted_at = Column(DateTime)  # When it was actually posted

    # AI metadata
    ai_generated = Column(Boolean, default=False)
    ai_confidence = Column(Integer)  # 0-100
    ai_metadata = Column(JSON, default={})  # Additional metadata (topics, rationale, etc.)

    # Error handling
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    x_account = relationship("XAccount")


class CronJob(Base):
    """
    Recurring workflow executions (cron jobs for agent automation)
    """
    __tablename__ = "cron_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Configuration
    name = Column(String, nullable=False)  # "Daily Reply Guy Strategy"
    assistant_id = Column(String, default="x_growth_deep_agent")

    # Scheduling
    schedule = Column(String, nullable=False)  # Cron expression "0 9 * * *"
    timezone = Column(String, default="UTC")
    next_run_at = Column(DateTime, nullable=True)  # Calculated from schedule

    # Workflow/Input
    workflow_id = Column(String, nullable=True)  # Optional: "reply_guy_strategy"
    custom_prompt = Column(Text, nullable=True)  # Optional: custom instructions
    input_config = Column(JSON, default={})  # Additional parameters

    # Status
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_run_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="cron_jobs")
    runs = relationship("CronJobRun", back_populates="cron_job", cascade="all, delete-orphan")


class CronJobRun(Base):
    """
    Execution history for cron jobs
    """
    __tablename__ = "cron_job_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cron_job_id = Column(Integer, ForeignKey("cron_jobs.id"), nullable=False)

    # Execution details
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String, default="running")  # running, completed, failed

    # LangGraph execution
    thread_id = Column(String, nullable=True)  # LangGraph thread ID

    # Error handling
    error_message = Column(Text, nullable=True)

    # Relationships
    cron_job = relationship("CronJob", back_populates="runs")


class WorkflowExecution(Base):
    """
    Workflow execution history for tracking progress and enabling resume/reconnection
    """
    __tablename__ = "workflow_executions"

    id = Column(String, primary_key=True)  # execution_id (UUID)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)  # Optional: may be null for test executions

    # Workflow info
    workflow_id = Column(String, nullable=False)
    workflow_name = Column(String)
    thread_id = Column(String, nullable=False)  # LangGraph thread ID

    # Execution state
    status = Column(String, default="running")  # running, completed, failed
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Progress tracking
    current_step = Column(Integer, default=0)
    total_steps = Column(Integer)
    completed_steps = Column(JSON, default=[])  # Array of step IDs/indices

    # Execution logs (optional - can be large, may want to limit size)
    logs = Column(JSON, default=[])  # Array of log entries
    error_message = Column(Text, nullable=True)

    # Relationships
    user = relationship("User")


# =============================================================================
# Ads Platform Integration Models
# =============================================================================

class AdsPlatform(Base):
    """
    Connected ads platform account (Meta Ads, Google Ads)
    """
    __tablename__ = "ads_platforms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Platform info
    platform = Column(String(20), nullable=False)  # "meta" or "google"
    account_id = Column(String(100))  # Platform-specific account ID (ad account ID)
    account_name = Column(String(255))

    # Meta-specific fields
    meta_page_id = Column(String(100))  # Facebook Page ID for ad attribution
    meta_business_id = Column(String(100))  # Business Manager ID

    # Google-specific fields
    google_mcc_id = Column(String(20))  # Manager Account (MCC) ID if applicable

    # Status
    is_connected = Column(Boolean, default=True)
    connection_error = Column(Text)  # Last error message if connection failed

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at = Column(DateTime)

    # Relationships
    user = relationship("User", backref="ads_platforms")
    credentials = relationship("AdsCredential", back_populates="platform", uselist=False, cascade="all, delete-orphan")
    campaigns = relationship("AdsCampaign", back_populates="platform", cascade="all, delete-orphan")


class AdsCredential(Base):
    """
    Encrypted OAuth tokens for ads platforms
    Uses Fernet encryption (same as UserCookies)
    """
    __tablename__ = "ads_credentials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_id = Column(Integer, ForeignKey("ads_platforms.id"), nullable=False)

    # Encrypted tokens (use services/cookie_encryption.py)
    encrypted_access_token = Column(Text)
    encrypted_refresh_token = Column(Text)

    # Token metadata
    token_expires_at = Column(DateTime)
    scopes = Column(JSON)  # List of granted permissions

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    platform = relationship("AdsPlatform", back_populates="credentials")


class AdsCampaign(Base):
    """
    Tracked ad campaigns across platforms
    """
    __tablename__ = "ads_campaigns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_id = Column(Integer, ForeignKey("ads_platforms.id"), nullable=False)

    # External campaign identifiers
    external_campaign_id = Column(String(100))  # Platform's campaign ID
    external_ad_set_id = Column(String(100))  # Ad Set ID (Meta) / Asset Group ID (Google)

    # Campaign details
    name = Column(String(255))
    campaign_type = Column(String(50))  # advantage_plus, performance_max, search, etc.
    objective = Column(String(50))  # conversions, traffic, awareness

    # Status
    status = Column(String(20), default="draft")  # draft, active, paused, archived, error

    # Budget (in cents to avoid floating point issues)
    daily_budget_cents = Column(Integer)
    lifetime_budget_cents = Column(Integer)
    total_spend_cents = Column(Integer, default=0)

    # Targeting (stored as JSON for flexibility)
    targeting = Column(JSON, default={})  # geo, age, interests, etc.

    # Creative info
    headline = Column(String(255))
    description = Column(Text)
    destination_url = Column(String(500))
    media_url = Column(String(500))  # Image or video URL

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at = Column(DateTime)
    started_at = Column(DateTime)  # When campaign was activated
    ended_at = Column(DateTime)  # When campaign was stopped

    # Relationships
    platform = relationship("AdsPlatform", back_populates="campaigns")
    metrics = relationship("AdsMetrics", back_populates="campaign", cascade="all, delete-orphan")


class AdsMetrics(Base):
    """
    Daily campaign performance metrics
    Synced from Meta/Google APIs
    """
    __tablename__ = "ads_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("ads_campaigns.id"), nullable=False)

    # Date for this metrics snapshot
    date = Column(Date, nullable=False)

    # Core metrics
    impressions = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    conversions = Column(Integer, default=0)

    # Financial metrics (in cents)
    spend_cents = Column(Integer, default=0)
    revenue_cents = Column(Integer, default=0)

    # Derived metrics (pre-calculated for reporting)
    ctr = Column(Float)  # Click-through rate (clicks/impressions)
    cpc_cents = Column(Integer)  # Cost per click
    cpa_cents = Column(Integer)  # Cost per acquisition
    roas = Column(Float)  # Return on ad spend (revenue/spend)

    # Timestamp
    synced_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    campaign = relationship("AdsCampaign", back_populates="metrics")


# =============================================================================
# CRM Models - Customer Tracking & Unified Inbox
# =============================================================================


class Customer(Base):
    """
    Customer/Contact record - the central entity in the CRM.
    One customer can have multiple conversations across channels.
    Phone number is the primary identifier (links WhatsApp to shop visits).
    """
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)  # Business owner

    # Identity (phone is primary key for matching)
    phone_number = Column(String(20), index=True)  # E.164 format (+1234567890)
    email = Column(String(255))
    instagram_id = Column(String(50))  # Instagram scoped user ID
    messenger_id = Column(String(50))  # Messenger PSID
    whatsapp_id = Column(String(50))  # WhatsApp phone number ID

    # Profile
    first_name = Column(String(100))
    last_name = Column(String(100))
    profile_picture_url = Column(String(500))

    # Attribution (which ad brought them)
    source_campaign_id = Column(Integer, ForeignKey("ads_campaigns.id"), nullable=True)
    source_ad_id = Column(String(100))  # External ad ID
    source_channel = Column(String(20))  # whatsapp, instagram, messenger, organic
    first_contact_at = Column(DateTime)
    utm_source = Column(String(100))
    utm_medium = Column(String(100))
    utm_campaign = Column(String(100))
    ctwa_clid = Column(String(100))  # Click-to-WhatsApp Click ID for CAPI

    # Customer journey stage
    lifecycle_stage = Column(String(20), default="lead")  # lead, prospect, customer, repeat, churned

    # Visit tracking (for review requests via QR code check-in)
    visit_count = Column(Integer, default=0)
    last_visit_at = Column(DateTime)
    total_spent_cents = Column(Integer, default=0)  # Lifetime value

    # Notes
    notes = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", backref="customers")
    source_campaign = relationship("AdsCampaign", backref="attributed_customers")
    tags = relationship("CustomerTag", back_populates="customer", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="customer", cascade="all, delete-orphan")
    followups = relationship("AutomatedFollowup", back_populates="customer", cascade="all, delete-orphan")
    conversion_events = relationship("ConversionEvent", back_populates="customer", cascade="all, delete-orphan")


class CustomerTag(Base):
    """
    Tags for customers - supports both smart (auto-generated) and manual tags.
    Examples: new_customer, returning, high_value, hot_lead, from_ad
    """
    __tablename__ = "customer_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)

    # Tag details
    name = Column(String(50), nullable=False)  # new_customer, returning, high_value, hot_lead, etc.
    category = Column(String(30), default="custom")  # lifecycle, behavior, source, custom
    color = Column(String(7), default="#3B82F6")  # Hex color for UI

    # Smart tag metadata
    is_smart_tag = Column(Boolean, default=False)
    smart_rule = Column(String(100))  # Rule that generated this: "visit_count >= 3"
    confidence = Column(Float)  # AI confidence if ML-generated

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)  # Some tags expire (e.g., "contacted_recently")

    # Relationships
    customer = relationship("Customer", back_populates="tags")


class Conversation(Base):
    """
    A conversation thread with a customer.
    One conversation = one channel thread (WhatsApp, IG DM, or Messenger).
    """
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Channel info
    channel = Column(String(20), nullable=False)  # whatsapp, instagram, messenger
    external_thread_id = Column(String(100))  # Platform-specific thread ID

    # Status
    status = Column(String(20), default="open")  # open, snoozed, closed, archived
    is_unread = Column(Boolean, default=True)
    requires_response = Column(Boolean, default=True)

    # 24-hour window tracking (Meta messaging rules)
    last_customer_message_at = Column(DateTime)  # When customer last messaged
    window_expires_at = Column(DateTime)  # 24hr window for free replies

    # Assignment
    assigned_to = Column(String)  # Could be user_id or "ai" for auto-replies

    # Context from ad click (CAPI data)
    source_ad_id = Column(String(100))
    source_campaign_id = Column(Integer, ForeignKey("ads_campaigns.id"))
    ctwa_clid = Column(String(100))  # Click-to-WhatsApp Click ID for CAPI

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_message_at = Column(DateTime)

    # Relationships
    customer = relationship("Customer", back_populates="conversations")
    user = relationship("User", backref="crm_conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    source_campaign_rel = relationship("AdsCampaign", foreign_keys=[source_campaign_id])


class Message(Base):
    """
    Individual messages within a conversation.
    Supports text, images, documents, and interactive messages.
    """
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)

    # Message identity
    external_message_id = Column(String(100), unique=True)  # Meta message ID (wamid)
    direction = Column(String(10), nullable=False)  # inbound, outbound

    # Content
    message_type = Column(String(20), default="text")  # text, image, video, audio, document, template, interactive, checkin
    content = Column(Text)  # Text content or caption
    media_url = Column(String(500))  # URL to media
    media_mime_type = Column(String(50))

    # Template info (for outbound)
    template_name = Column(String(100))
    template_params = Column(JSON)

    # AI-drafted reply metadata
    is_ai_drafted = Column(Boolean, default=False)
    ai_draft_approved = Column(Boolean)  # null = pending, True = sent, False = edited/rejected
    ai_confidence = Column(Float)

    # Delivery status (for outbound)
    status = Column(String(20), default="pending")  # pending, sent, delivered, read, failed
    status_timestamp = Column(DateTime)
    error_code = Column(String(50))
    error_message = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime)
    delivered_at = Column(DateTime)
    read_at = Column(DateTime)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")


class ConversionEvent(Base):
    """
    Tracks conversion events for CAPI attribution.
    Links customer actions to ad campaigns.
    Events: Lead, Visit, Purchase, CompleteRegistration, etc.
    """
    __tablename__ = "conversion_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Event details
    event_name = Column(String(50), nullable=False)  # Lead, Visit, Purchase, CompleteRegistration, etc.
    event_source = Column(String(20), default="crm")  # crm, pos, website, manual, checkin

    # Value
    value_cents = Column(Integer, default=0)
    currency = Column(String(3), default="USD")

    # Attribution
    campaign_id = Column(Integer, ForeignKey("ads_campaigns.id"))
    ad_set_id = Column(String(100))
    ad_id = Column(String(100))
    click_id = Column(String(100))  # fbclid, ctwa_clid
    attribution_window = Column(String(20))  # 1d_click, 7d_click, 1d_view

    # CAPI sync status
    capi_event_id = Column(String(100))  # Unique event ID for deduplication
    capi_synced_at = Column(DateTime)
    capi_response = Column(JSON)

    # Timestamps
    event_time = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    customer = relationship("Customer", back_populates="conversion_events")
    user = relationship("User", backref="conversion_events")
    campaign = relationship("AdsCampaign", backref="crm_conversion_events")


class AutomatedFollowup(Base):
    """
    Scheduled automated follow-up messages.
    Supports review requests, dormant client reminders, etc.
    """
    __tablename__ = "automated_followups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Followup type
    followup_type = Column(String(30), nullable=False)  # review_request, visit_reminder, dormant_reactivation, custom
    template_name = Column(String(100))  # WhatsApp template to use

    # Scheduling
    scheduled_at = Column(DateTime, nullable=False)
    send_channel = Column(String(20), default="whatsapp")  # whatsapp, instagram, messenger

    # Status
    status = Column(String(20), default="scheduled")  # scheduled, sent, cancelled, failed
    sent_at = Column(DateTime)
    message_id = Column(Integer, ForeignKey("messages.id"))  # Link to sent message

    # Trigger context
    trigger_event = Column(String(50))  # visit_completed, purchase, 30_days_inactive
    trigger_data = Column(JSON)  # Additional context

    # Error handling
    retry_count = Column(Integer, default=0)
    last_error = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    customer = relationship("Customer", back_populates="followups")
    user = relationship("User", backref="automated_followups")
    message = relationship("Message")


class MessagingPlatform(Base):
    """
    Connected messaging platform credentials.
    Stores WhatsApp Business Account, Instagram, and Messenger page info.
    """
    __tablename__ = "messaging_platforms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Platform type
    platform = Column(String(20), nullable=False)  # meta (covers WhatsApp, IG, Messenger)

    # WhatsApp Business Account
    waba_id = Column(String(50))  # WhatsApp Business Account ID
    phone_number_id = Column(String(50))  # WhatsApp phone number ID
    phone_number = Column(String(20))  # Display phone number

    # Instagram
    instagram_account_id = Column(String(50))
    instagram_username = Column(String(50))

    # Facebook Page (for Messenger)
    page_id = Column(String(50))
    page_name = Column(String(100))

    # Webhook verification
    webhook_verify_token = Column(String(64))  # Generated per user for webhook verification

    # Check-in code for QR
    checkin_code = Column(String(50), unique=True)  # Unique code like "mario123" for CHECKIN_mario123

    # Status
    is_connected = Column(Boolean, default=True)
    connection_error = Column(Text)
    scopes = Column(JSON)  # List of granted permissions

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at = Column(DateTime)

    # Relationships
    user = relationship("User", backref="messaging_platforms")
    credentials = relationship("MessagingCredential", back_populates="platform", uselist=False, cascade="all, delete-orphan")


class MessagingCredential(Base):
    """
    Encrypted OAuth tokens for messaging platforms.
    Similar to AdsCredential but for messaging scopes.
    """
    __tablename__ = "messaging_credentials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_id = Column(Integer, ForeignKey("messaging_platforms.id"), nullable=False)

    # Encrypted tokens (using same encryption as AdsCredential)
    encrypted_access_token = Column(Text)
    encrypted_system_user_token = Column(Text)  # For WhatsApp Cloud API
    encrypted_page_access_token = Column(Text)  # Page-specific token for Messenger

    # Token metadata
    token_expires_at = Column(DateTime)
    scopes = Column(JSON)  # whatsapp_business_messaging, instagram_manage_messages, pages_messaging, etc.

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    platform = relationship("MessagingPlatform", back_populates="credentials")


# =============================================================================
# Image Generation & Asset Management Models
# =============================================================================


class UserAsset(Base):
    """
    User's brand assets for AI image generation.
    Examples: company logo, product photos, background images.
    These can be used as image_input for Nano Banana Pro.
    """
    __tablename__ = "user_assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Asset info
    name = Column(String(100), nullable=False)  # "Company Logo", "Pepperoni Pizza"
    asset_type = Column(String(30), default="other")  # logo, product, background, other
    description = Column(Text)  # Optional description

    # File info
    file_url = Column(String(500), nullable=False)  # Cloud storage URL
    thumbnail_url = Column(String(500))  # Smaller preview URL
    file_size_bytes = Column(Integer)
    mime_type = Column(String(50))  # image/png, image/jpeg

    # Image dimensions
    width = Column(Integer)
    height = Column(Integer)

    # Status
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", backref="assets")


class ImageGenerationJob(Base):
    """
    Tracks AI image generation jobs via Nano Banana Pro (Kie.ai).
    Each job represents one image generation request.
    """
    __tablename__ = "image_generation_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    campaign_id = Column(Integer, ForeignKey("ads_campaigns.id"), nullable=True)

    # External task tracking
    external_task_id = Column(String(100))  # Kie.ai task ID

    # Generation parameters
    prompt = Column(Text, nullable=False)  # The text prompt
    aspect_ratio = Column(String(10), default="1:1")  # 1:1, 16:9, 9:16, 4:3, 3:4, 4:5, 5:4, 21:9, 9:21
    resolution = Column(String(10), default="1k")  # 1k, 2k
    input_asset_ids = Column(JSON, default=[])  # Array of UserAsset IDs used as image_input

    # Status
    status = Column(String(20), default="pending")  # pending, processing, completed, failed
    error_message = Column(Text)

    # Result
    result_url = Column(String(500))  # Generated image URL
    result_width = Column(Integer)
    result_height = Column(Integer)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    # Relationships
    user = relationship("User", backref="image_generation_jobs")
    campaign = relationship("AdsCampaign", backref="image_generation_jobs")


# =============================================================================
# Billing & Subscription Models
# =============================================================================


class Subscription(Base):
    """
    Stripe subscription tracking.
    Links users to their Stripe subscriptions and tracks billing status.
    """
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)

    # Stripe identifiers
    stripe_subscription_id = Column(String(100), unique=True)
    stripe_price_id = Column(String(100))

    # Plan details
    plan = Column(String(20), nullable=False)  # pro, pro_plus, ultimate
    status = Column(String(20), default="active")  # active, past_due, canceled, trialing, incomplete

    # Billing cycle
    current_period_start = Column(DateTime)
    current_period_end = Column(DateTime)
    cancel_at_period_end = Column(Boolean, default=False)
    canceled_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="subscription")
    credit_balance = relationship("CreditBalance", back_populates="subscription", uselist=False, cascade="all, delete-orphan")


class CreditBalance(Base):
    """
    Track user's credit balance for usage-based billing.
    Credits are consumed by Claude API calls, computer use, and image generation.
    """
    __tablename__ = "credit_balances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=False, unique=True)

    # Credit tracking
    monthly_allocation = Column(Integer, nullable=False)  # Credits included in plan
    credits_used = Column(Integer, default=0)  # Credits consumed this period
    credits_purchased = Column(Integer, default=0)  # Additional purchased credits (one-time)

    # Overage tracking (for Stripe metered billing)
    overage_credits = Column(Integer, default=0)

    # Reset tracking
    last_reset_at = Column(DateTime, default=datetime.utcnow)
    next_reset_at = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    subscription = relationship("Subscription", back_populates="credit_balance")


class CreditTransaction(Base):
    """
    Audit log for all credit transactions.
    Records usage, allocations, purchases, and refunds.
    """
    __tablename__ = "credit_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Transaction details
    transaction_type = Column(String(30), nullable=False)  # usage, allocation, purchase, refund, reset
    credits = Column(Integer, nullable=False)  # Positive for additions, negative for usage

    # Context
    description = Column(String(255))
    endpoint = Column(String(100))  # API endpoint that consumed credits
    agent_type = Column(String(50))  # x_growth, ads, crm, content_engine

    # Stripe reference (for purchases)
    stripe_invoice_id = Column(String(100))

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", backref="credit_transactions")


class FeatureUsage(Base):
    """
    Track feature-specific usage for gating.
    Counts usage per feature per billing period.
    """
    __tablename__ = "feature_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Feature tracking (monthly)
    feature = Column(String(50), nullable=False)  # x_growth_sessions, content_generations, ads_campaigns, etc.
    count = Column(Integer, default=0)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", backref="feature_usage")

