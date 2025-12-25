"""
CRM Service Configuration

Settings for Meta messaging APIs (WhatsApp, Instagram, Messenger)
and Conversions API (CAPI) for attribution.
"""

import os
from pydantic_settings import BaseSettings
from typing import Optional, List


# =============================================================================
# Meta Messaging OAuth Scopes
# =============================================================================

# Additional scopes needed for messaging (extend existing Meta Ads OAuth)
MESSAGING_SCOPES = [
    # WhatsApp Business
    "whatsapp_business_management",
    "whatsapp_business_messaging",
    # Instagram
    "instagram_basic",
    "instagram_manage_messages",
    # Facebook Messenger
    "pages_messaging",
    "pages_manage_metadata",
    "pages_read_engagement",
]

# Combined scopes for full CRM + Ads functionality
FULL_META_SCOPES = [
    # Ads scopes (from ads_service)
    "ads_management",
    "ads_read",
    "business_management",
    # Messaging scopes
    *MESSAGING_SCOPES,
]


# =============================================================================
# CAPI Event Types
# =============================================================================

CAPI_EVENTS = {
    "lead": "Lead",
    "visit": "Visit",  # Custom event for physical visits
    "purchase": "Purchase",
    "add_to_cart": "AddToCart",
    "complete_registration": "CompleteRegistration",
}


# =============================================================================
# Settings Class
# =============================================================================


class CRMSettings(BaseSettings):
    """Settings for CRM Service integrations."""

    # ==========================================================================
    # Meta Messaging Configuration
    # ==========================================================================

    # Reuse Meta App credentials from ads_service
    meta_app_id: Optional[str] = None
    meta_app_secret: Optional[str] = None

    # Meta API version (should match ads_service)
    meta_api_version: str = "v22.0"

    # Webhook verification token (generate unique per deployment)
    meta_webhook_verify_token: Optional[str] = None

    # ==========================================================================
    # WhatsApp Cloud API
    # ==========================================================================

    # WhatsApp Business Account ID (set during OAuth)
    # Each user will have their own, stored in MessagingPlatform
    whatsapp_phone_number_id: Optional[str] = None

    # ==========================================================================
    # Meta Conversions API (CAPI)
    # ==========================================================================

    # Pixel ID for server-side events
    meta_pixel_id: Optional[str] = None

    # Access token with CAPI permissions
    meta_capi_access_token: Optional[str] = None

    # Test event code (for development - events go to test panel)
    meta_capi_test_code: Optional[str] = None

    # ==========================================================================
    # Automated Follow-ups
    # ==========================================================================

    # Hours after visit to send review request
    review_request_delay_hours: int = 24

    # Days without visit to consider customer dormant
    dormant_threshold_days: int = 30

    # ==========================================================================
    # QR Check-in Settings
    # ==========================================================================

    # Prefix for check-in messages
    checkin_message_prefix: str = "CHECKIN_"

    # Auto-reply template after check-in
    checkin_auto_reply: str = "Thanks for checking in! Enjoy your visit! 🎉"

    # ==========================================================================
    # General Settings
    # ==========================================================================

    # Base URL for webhook callbacks
    app_base_url: str = "http://localhost:8002"

    # Encryption key (reuse from ads_service)
    encryption_key: Optional[str] = None

    # Redis URL for caching
    redis_url: str = "redis://localhost:6379"

    class Config:
        env_prefix = ""
        case_sensitive = False
        env_file = ".env"
        extra = "ignore"


# Singleton instance
_settings: Optional[CRMSettings] = None


def get_crm_settings() -> CRMSettings:
    """Get the CRM settings singleton."""
    global _settings
    if _settings is None:
        _settings = CRMSettings()
    return _settings


# =============================================================================
# Helper Functions
# =============================================================================


def is_messaging_configured() -> bool:
    """Check if Meta messaging credentials are configured."""
    settings = get_crm_settings()
    return bool(settings.meta_app_id and settings.meta_app_secret)


def is_capi_configured() -> bool:
    """Check if CAPI is configured for attribution."""
    settings = get_crm_settings()
    return bool(settings.meta_pixel_id and settings.meta_capi_access_token)


def get_messaging_oauth_url(state: str, redirect_uri: str) -> str:
    """Generate OAuth URL with messaging scopes."""
    settings = get_crm_settings()
    scopes = ",".join(MESSAGING_SCOPES)

    return (
        f"https://www.facebook.com/{settings.meta_api_version}/dialog/oauth?"
        f"client_id={settings.meta_app_id}&"
        f"redirect_uri={redirect_uri}&"
        f"state={state}&"
        f"scope={scopes}&"
        f"response_type=code"
    )
