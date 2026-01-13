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

    # Source tracking: 'agent' = AI-generated, 'manual' = user posted directly, 'imported' = backfilled
    source = Column(String(20), default="imported")

    # Metadata
    posted_at = Column(DateTime)
    imported_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    x_account = relationship("XAccount", back_populates="posts")


class UserComment(Base):
    """
    Track comments WE make on other people's posts and their engagement.
    Used for measuring the effectiveness of the Reply Guy strategy.
    """
    __tablename__ = "user_comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    x_account_id = Column(Integer, ForeignKey("x_accounts.id"), nullable=False)

    # Our comment content
    content = Column(Text, nullable=False)
    comment_url = Column(String(500))  # Direct URL to our comment/reply

    # Target post info (the post we commented on)
    target_post_url = Column(String(500))
    target_post_author = Column(String(100))
    target_post_content_preview = Column(String(500))  # Preview of post we replied to

    # Engagement OUR comment receives
    likes = Column(Integer, default=0)
    replies = Column(Integer, default=0)
    retweets = Column(Integer, default=0)
    impressions = Column(Integer, default=0)  # If available from X analytics

    # Source tracking: 'agent' = AI-generated, 'manual' = user posted directly, 'imported' = backfilled
    source = Column(String(20), default="imported")

    # Scraping metadata
    last_scraped_at = Column(DateTime)
    scrape_status = Column(String(20), default="pending")  # pending, success, failed, not_found
    scrape_error = Column(Text)

    # Timestamps
    commented_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    x_account = relationship("XAccount", backref="comments_made")


class ReceivedComment(Base):
    """
    Track comments OTHERS leave on our posts.
    Useful for identifying engaged followers and responding to engagement.
    """
    __tablename__ = "received_comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_post_id = Column(Integer, ForeignKey("user_posts.id"), nullable=False)
    x_account_id = Column(Integer, ForeignKey("x_accounts.id"), nullable=False)

    # Commenter info
    commenter_username = Column(String(100), nullable=False)
    commenter_display_name = Column(String(255))
    comment_url = Column(String(500))

    # Comment content
    content = Column(Text)

    # Engagement on the comment
    likes = Column(Integer, default=0)
    replies = Column(Integer, default=0)

    # Did we reply to this comment?
    we_replied = Column(Boolean, default=False)
    our_reply_url = Column(String(500))

    # Scraping metadata
    last_scraped_at = Column(DateTime)

    # Timestamps
    commented_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user_post = relationship("UserPost", backref="comments_received")
    x_account = relationship("XAccount", backref="comments_received")


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


# =============================================================================
# Style Learning & Continual Learning Models
# =============================================================================


class StyleFeedback(Base):
    """
    Track user feedback on AI-generated content for continual learning.

    This table captures:
    - Explicit feedback (thumbs up/down, text comments)
    - Implicit feedback (edits made before posting)
    - Approval/rejection rates

    The feedback is used by FeedbackProcessor to:
    - Learn banned phrases from removed text
    - Learn positive patterns from approved content
    - Adjust style matching weights

    Based on Letta's continual learning principles:
    - Learning in Token Space (patterns stored as memory, not fine-tuning)
    - Sleep-time Compute (daily consolidation of feedback into rules)
    """
    __tablename__ = "style_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    x_account_id = Column(Integer, ForeignKey("x_accounts.id"), nullable=True)

    # Generation details
    generation_type = Column(String(20), nullable=False)  # post, comment, thread
    generation_id = Column(String(100))  # External ID if applicable

    # Content tracking
    original_content = Column(Text, nullable=False)  # AI-generated content
    edited_content = Column(Text)  # User's edited version (if modified)

    # Feedback classification
    action = Column(String(20), nullable=False)  # approved, edited, rejected, regenerated
    edit_distance = Column(Float)  # Levenshtein distance ratio (0-1)

    # Explicit feedback
    rating = Column(Integer)  # 1-5 stars or thumbs (1=down, 5=up)
    feedback_text = Column(Text)  # Optional user comments
    feedback_tags = Column(JSON, default=[])  # ["too_formal", "wrong_tone", "ai_sounding"]

    # Analysis results (filled by FeedbackProcessor)
    removed_phrases = Column(JSON, default=[])  # Phrases user removed
    added_phrases = Column(JSON, default=[])  # Phrases user added
    learned_patterns = Column(JSON, default={})  # Extracted patterns

    # Processing status
    processed = Column(Boolean, default=False)  # Has been processed by consolidation
    processed_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", backref="style_feedbacks")
    x_account = relationship("XAccount", backref="style_feedbacks")


class StyleEvolutionSnapshot(Base):
    """
    Versioned snapshots of user's writing style for drift detection.

    This table enables:
    - Style versioning (rollback capability)
    - Drift detection (compare current vs historical style)
    - Time-weighted profile calculation

    Each snapshot captures the full DeepStyleProfile at a point in time.
    Snapshots are created when:
    - User imports new posts (>10 new samples)
    - Significant drift is detected
    - Manual recalculation is triggered
    - Daily style check finds changes
    """
    __tablename__ = "style_evolution_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Snapshot identification
    snapshot_id = Column(String(50), unique=True, nullable=False)  # format: user_id_YYYYMMDD_HHmmss

    # Style profile (full DeepStyleProfile as JSON)
    profile_json = Column(JSON, nullable=False)

    # Context at snapshot time
    post_count_at_snapshot = Column(Integer, default=0)  # Total posts analyzed
    comment_count_at_snapshot = Column(Integer, default=0)  # Total comments analyzed

    # Trigger information
    trigger = Column(String(50), default="manual")  # manual, drift_detected, new_posts, scheduled

    # Drift metrics (compared to previous snapshot)
    drift_from_previous = Column(Float)  # Overall drift score 0-1
    drift_details = Column(JSON, default={})  # Per-dimension drift scores

    # Status
    is_active = Column(Boolean, default=True)  # Is this the current active profile?

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", backref="style_evolution_snapshots")


# =============================================================================
# Learning Engine - Recommendation & Preference Models
# =============================================================================


class PostRecommendation(Base):
    """
    Tracks posts recommended to users → their decisions → engagement outcomes.

    This is the core training data for the generative recommender (A-SFT style).
    Each record captures:
    1. What was shown (post + score + reason)
    2. User's decision (yes/no) + structured reasons WHY
    3. Outcome (did engagement succeed?)

    The "advantage" for training = actual_outcome - predicted_score
    """
    __tablename__ = "post_recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    x_account_id = Column(Integer, ForeignKey("x_accounts.id"), nullable=True)

    # Post data (denormalized for fast access)
    post_url = Column(String(500), nullable=False)
    post_author = Column(String(100))
    post_content_preview = Column(Text)  # First 500 chars
    post_likes = Column(Integer, default=0)
    post_retweets = Column(Integer, default=0)
    post_replies = Column(Integer, default=0)
    post_hours_ago = Column(Float)  # Age when recommended

    # Recommendation metadata
    batch_id = Column(String(50), index=True)  # Groups carousel items together
    position_in_batch = Column(Integer)  # Position in carousel (0-indexed)
    recommendation_score = Column(Float)  # Model's predicted probability
    recommendation_reason = Column(Text)  # "Matches your interest in AI"
    feature_vector = Column(JSON, default={})  # Features used for scoring

    # User's decision
    action = Column(String(20), default="pending")  # pending, selected, skipped, not_interested
    action_at = Column(DateTime, nullable=True)

    # Structured feedback (A-SFT training data)
    feedback_decision = Column(String(10))  # "yes" or "no" explicit answer
    feedback_reasons = Column(JSON, default=[])  # List of reason IDs selected
    feedback_features = Column(JSON, default={})  # Aggregated feature signals from reasons
    other_reason = Column(Text)  # Free-text "other" reason
    time_to_decide_ms = Column(Integer)  # Engagement signal: how long user took

    # Engagement outcome (filled after user engages)
    engagement_type = Column(String(20))  # liked, commented, quoted, retweeted
    engagement_content = Column(Text)  # Our comment/quote text if applicable
    comment_url = Column(String(500))  # URL to our comment

    # Outcome metrics (for reward calculation)
    outcome_likes = Column(Integer, default=0)  # Likes on OUR engagement
    outcome_replies = Column(Integer, default=0)  # Replies to OUR engagement
    outcome_retweets = Column(Integer, default=0)
    outcome_scraped_at = Column(DateTime)  # When we checked outcome
    engagement_success = Column(Boolean)  # Derived: outcome > 0

    # A-SFT training fields
    advantage = Column(Float)  # actual_outcome - predicted_score
    training_weight = Column(Float, default=1.0)  # Weight for training

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", backref="post_recommendations")
    x_account = relationship("XAccount", backref="post_recommendations")


class PreferenceSignal(Base):
    """
    Aggregated preference signals learned from user behavior.

    These are the "learned priors" for the recommender:
    - topic_preference: "AI" → positive_count=15, negative_count=2
    - author_preference: "@sama" → high engagement success rate
    - format_preference: "threads" → user likes long-form

    Updated incrementally after each user action (online learning).
    Decayed daily to adapt to changing preferences.
    """
    __tablename__ = "preference_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Signal identification
    signal_type = Column(String(30), nullable=False)  # topic_preference, author_preference, format_preference, reason_preference
    signal_value = Column(String(255), nullable=False)  # "AI", "@sama", "threads", "topic_match"

    # Counts (for Bayesian updates)
    positive_count = Column(Integer, default=0)  # Times user engaged with this
    negative_count = Column(Integer, default=0)  # Times user skipped this
    total_shown = Column(Integer, default=0)  # Total times shown

    # Derived scores
    preference_score = Column(Float, default=0.5)  # 0-1, computed from counts
    confidence = Column(Float, default=0.0)  # Higher with more samples
    engagement_success_rate = Column(Float)  # When engaged, how often successful?

    # Temporal tracking
    last_positive_at = Column(DateTime)
    last_negative_at = Column(DateTime)
    decay_factor = Column(Float, default=1.0)  # Applied daily (0.95^days)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", backref="preference_signals")


class RecommendationModel(Base):
    """
    Versioned preference model per user.

    Stores the trained model state for the generative recommender.
    Each user has one active model, with version history for rollback.

    Model types:
    - "feature_weights": Simple linear weights on preference signals
    - "embedding": User preference embedding (1536 dims from OpenAI)
    - "bandit": Serialized contextual bandit model
    - "llm_profile": Text summary of preferences for LLM-based ranking
    """
    __tablename__ = "recommendation_models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Model identification
    model_type = Column(String(30), default="feature_weights")  # feature_weights, embedding, bandit, llm_profile
    model_version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)  # Only one active per user per type

    # Model content (varies by type)
    feature_weights = Column(JSON, default={})  # {"topic_relevance": 0.3, "author_preference": 0.25, ...}
    embedding = Column(JSON)  # User preference embedding as list of floats
    model_weights = Column(Text)  # Serialized bandit model (base64)
    llm_profile = Column(Text)  # Text summary for LLM-based ranking

    # Training metadata
    training_samples = Column(Integer, default=0)
    last_trained_at = Column(DateTime)
    training_config = Column(JSON, default={})  # Hyperparameters used

    # Performance metrics
    avg_advantage = Column(Float)  # Average advantage on recent predictions
    hit_rate = Column(Float)  # % of recommendations user engaged with
    metrics_updated_at = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", backref="recommendation_models")


class LearnedStyleRule(Base):
    """
    Consolidated learned rules from user feedback.

    These rules are the output of FeedbackProcessor's consolidation step.
    They are applied during content generation as additional constraints.

    Rule types:
    - banned_phrase: Never use this phrase
    - preferred_phrase: Use this phrase when possible
    - tone_adjustment: Adjust tone in this direction
    - length_preference: User prefers this length range
    - vocabulary_preference: Use/avoid specific vocabulary
    """
    __tablename__ = "learned_style_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Rule details
    rule_type = Column(String(30), nullable=False)  # banned_phrase, preferred_phrase, tone_adjustment, etc.
    rule_content = Column(Text, nullable=False)  # The phrase or instruction

    # Confidence and source
    confidence = Column(Float, default=0.5)  # 0-1, higher = more certain
    source_feedback_count = Column(Integer, default=1)  # How many feedbacks support this rule
    source_feedback_ids = Column(JSON, default=[])  # IDs of supporting feedbacks

    # Priority and status
    priority = Column(Integer, default=1)  # Higher = more important
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_applied_at = Column(DateTime, nullable=True)  # When this rule was last used

    # Relationships
    user = relationship("User", backref="learned_style_rules")


# =============================================================================
# Work Integrations Models - Build in Public Automation
# =============================================================================


class WorkIntegration(Base):
    """
    Connected work platforms for automatic activity capture.

    Each integration represents a connection to a developer platform
    (GitHub, Slack, Notion, Linear, Figma) where user activity is tracked
    and used to generate "build in public" X posts.

    Similar to AdsPlatform, but focused on work activity capture.
    """
    __tablename__ = "work_integrations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Platform identification
    platform = Column(String(20), nullable=False)  # github, slack, notion, linear, figma
    external_account_id = Column(String(100))  # Platform's account/org ID
    external_account_name = Column(String(255))  # Display name (GitHub username, Slack workspace, etc.)

    # Platform-specific configuration
    github_repos = Column(JSON, default=[])  # List of repo names to track ["owner/repo1", "owner/repo2"]
    github_org = Column(String(100))  # GitHub organization name (optional)
    slack_channels = Column(JSON, default=[])  # List of channel IDs to monitor
    slack_workspace_id = Column(String(50))  # Slack workspace ID
    notion_database_ids = Column(JSON, default=[])  # List of database IDs to track
    linear_team_id = Column(String(50))  # Linear team ID
    figma_project_ids = Column(JSON, default=[])  # List of Figma project IDs

    # Webhook configuration
    webhook_secret = Column(String(64))  # For verifying incoming webhooks
    webhook_registered = Column(Boolean, default=False)  # Has webhook been set up on platform?
    webhook_url = Column(String(500))  # The webhook URL we gave to the platform

    # Status
    is_connected = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)  # Can be paused without disconnecting
    connection_error = Column(Text)  # Last error message if connection failed
    scopes = Column(JSON, default=[])  # OAuth scopes granted

    # Activity capture settings
    capture_commits = Column(Boolean, default=True)
    capture_prs = Column(Boolean, default=True)
    capture_releases = Column(Boolean, default=True)
    capture_issues = Column(Boolean, default=True)
    capture_comments = Column(Boolean, default=True)

    # Billing (credits consumed per month)
    credits_per_month = Column(Integer, default=100)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at = Column(DateTime)
    last_activity_at = Column(DateTime)  # When last activity was captured

    # Relationships
    user = relationship("User", backref="work_integrations")
    credentials = relationship("WorkIntegrationCredential", back_populates="integration", uselist=False, cascade="all, delete-orphan")
    activities = relationship("WorkActivity", back_populates="integration", cascade="all, delete-orphan")


class WorkIntegrationCredential(Base):
    """
    Encrypted OAuth tokens for work integrations.

    Follows same pattern as AdsCredential - uses Fernet encryption
    via services/cookie_encryption.py.
    """
    __tablename__ = "work_integration_credentials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    integration_id = Column(Integer, ForeignKey("work_integrations.id"), nullable=False)

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
    integration = relationship("WorkIntegration", back_populates="credentials")


class WorkActivity(Base):
    """
    Captured work activities normalized across platforms.

    All activities from GitHub, Slack, Notion, Linear, Figma are stored
    in this unified format for processing by the draft generator.

    Activity lifecycle:
    1. Captured from webhook/poll → processed=False
    2. Daily aggregator scores and groups activities
    3. Draft generator creates ActivityDraft from activities
    4. Activities marked as processed=True
    """
    __tablename__ = "work_activities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    integration_id = Column(Integer, ForeignKey("work_integrations.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Activity identification
    platform = Column(String(20), nullable=False)  # github, slack, notion, linear, figma
    external_id = Column(String(100))  # Platform's unique ID for this activity
    activity_type = Column(String(50), nullable=False)  # pr_merged, commit_pushed, release_published, issue_closed, etc.
    category = Column(String(30), default="progress")  # code_shipped, progress, collaboration

    # Content
    title = Column(String(500), nullable=False)  # Short title of activity
    description = Column(Text)  # Longer description if available
    url = Column(String(500))  # Link to the activity on the platform
    repo_or_project = Column(String(200))  # Repository name, project name, etc.

    # Metrics (for significance scoring)
    lines_added = Column(Integer, default=0)
    lines_removed = Column(Integer, default=0)
    files_changed = Column(Integer, default=0)
    comments_count = Column(Integer, default=0)
    reactions_count = Column(Integer, default=0)

    # Significance scoring (calculated by aggregator)
    significance_score = Column(Float, default=0.0)  # 0.0 - 1.0

    # Raw payload (for debugging/reprocessing)
    raw_payload = Column(JSON, default={})

    # Processing status
    processed = Column(Boolean, default=False)
    processed_at = Column(DateTime)
    draft_id = Column(Integer, ForeignKey("activity_drafts.id", use_alter=True), nullable=True)  # Which draft used this activity

    # Timestamps
    activity_at = Column(DateTime, nullable=False)  # When the activity happened on the platform
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    integration = relationship("WorkIntegration", back_populates="activities")
    user = relationship("User", backref="work_activities")


class ActivityDraft(Base):
    """
    AI-generated post drafts from work activities.

    Created by the daily aggregator + draft generator service.
    Users review drafts in the UI and can approve, edit, or reject.

    Draft lifecycle:
    1. pending: Just created, waiting for user review
    2. approved: User approved, becomes a ScheduledPost
    3. edited: User modified and approved
    4. rejected: User rejected, will not be posted
    5. expired: 7 days passed without action
    """
    __tablename__ = "activity_drafts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    x_account_id = Column(Integer, ForeignKey("x_accounts.id"), nullable=False)

    # Generated content
    content = Column(Text, nullable=False)  # The draft post content
    ai_rationale = Column(Text)  # Why AI wrote it this way

    # Source activities
    source_activity_ids = Column(JSON, default=[])  # List of WorkActivity IDs used
    activity_summary = Column(Text)  # Summary of activities used for generation

    # Digest metadata
    digest_date = Column(Date, nullable=False)  # Which day's activities this covers
    digest_theme = Column(String(100))  # Theme detected (shipping, debugging, learning, etc.)

    # Status
    status = Column(String(20), default="pending")  # pending, approved, edited, rejected, expired, scheduled, posted
    user_edited_content = Column(Text)  # If user edited before approving

    # Scheduling (if approved)
    scheduled_post_id = Column(Integer, ForeignKey("scheduled_posts.id"), nullable=True)
    scheduled_at = Column(DateTime)
    posted_at = Column(DateTime)

    # Expiration
    expires_at = Column(DateTime)  # 7 days after creation by default

    # User feedback for style learning
    feedback_rating = Column(Integer)  # 1-5 stars
    feedback_text = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    reviewed_at = Column(DateTime)  # When user took action

    # Relationships
    user = relationship("User", backref="activity_drafts")
    x_account = relationship("XAccount", backref="activity_drafts")
    scheduled_post = relationship("ScheduledPost", backref="activity_draft")



# ============================================================================
# Voice Agent Booking (POC for SDR outreach)
# ============================================================================

class PendingBooking(Base):
    """
    Booking form for voice agent POC.
    Prospects fill this out during/after sales call to confirm meeting details.
    """
    __tablename__ = "pending_bookings"

    id = Column(String(12), primary_key=True)  # Short ID for URL: abc123de
    call_session_id = Column(String(100))       # Twilio Call SID (for webhook routing)
    webhook_url = Column(String(500))           # Voice agent callback URL
    phone_number = Column(String(20), nullable=False)  # Prospect's phone (E.164)

    # Proposed meeting time (from voice agent)
    proposed_datetime = Column(DateTime)

    # Prospect fills these in via form
    contact_name = Column(String(255))
    contact_email = Column(String(255))
    company_name = Column(String(255))
    selected_datetime = Column(DateTime)  # Can edit proposed time

    # Status tracking
    status = Column(String(20), default="pending")  # pending, submitted, expired

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    submitted_at = Column(DateTime)
    expires_at = Column(DateTime)  # created_at + 1 hour


# ============================================================================
# Early Access Requests (Lead Qualification)
# ============================================================================

class EarlyAccessRequest(Base):
    """
    Early access request submissions from the blog/landing page.
    Captures qualified leads with their context and preferences.
    """
    __tablename__ = "early_access_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False)

    # Qualification data
    role = Column(String(50))  # founder_operator, solo_builder, smb_owner, marketer_growth, other
    platform = Column(String(50))  # x_twitter, linkedin, local_business, customer_messages, figuring_out
    main_concern = Column(Text)  # Free text: what worries them about automation
    philosophy = Column(String(20))  # growth_first or trust_first
    manual_first_ok = Column(String(20))  # yes, depends, no
    open_to_conversation = Column(String(20))  # yes, maybe, no

    # Optional fields
    additional_notes = Column(Text)
    linkedin_url = Column(String(500))

    # Tracking
    source = Column(String(50), default="blog")  # Where they came from

    # Status (for internal use)
    status = Column(String(20), default="new")  # new, contacted, qualified, not_fit
    notes = Column(Text)  # Internal notes

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
