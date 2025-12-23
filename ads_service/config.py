"""
Ads Service Configuration

Environment variables for Meta and Google Ads API integration.
"""

import os
from pydantic_settings import BaseSettings
from typing import Optional


class AdsSettings(BaseSettings):
    """Settings for Ads Service integrations."""

    # ==========================================================================
    # Meta Ads Configuration
    # ==========================================================================

    # Meta App credentials (from developers.facebook.com)
    meta_app_id: Optional[str] = None
    meta_app_secret: Optional[str] = None

    # OAuth callback URL (production uses backend-api directly)
    meta_redirect_uri: str = os.getenv(
        "META_REDIRECT_URI",
        "https://backend-api-bw5qfm5d5a-uc.a.run.app/api/ads/oauth/meta/callback"
    )

    # Meta API version (latest stable)
    meta_api_version: str = "v22.0"

    # Parallel Universe's Business Manager ID (for System User tokens)
    meta_business_id: Optional[str] = None

    # ==========================================================================
    # Google Ads Configuration
    # ==========================================================================

    # Google Cloud OAuth credentials
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None

    # Google Ads API Developer Token (from API Center)
    google_developer_token: Optional[str] = None

    # Manager Account (MCC) Customer ID
    google_mcc_id: Optional[str] = None

    # OAuth callback URL
    google_redirect_uri: str = "http://localhost:8002/api/ads/oauth/google/callback"

    # Google Ads API login customer ID (usually same as MCC)
    google_login_customer_id: Optional[str] = None

    # ==========================================================================
    # General Settings
    # ==========================================================================

    # Base URL for the application (for OAuth callbacks)
    app_base_url: str = os.getenv("APP_BASE_URL", "https://app.paralleluniverse.ai")

    # Redis URL for OAuth state storage
    redis_url: str = os.getenv("REDIS_URL", f"redis://{os.getenv('REDIS_HOST', 'localhost')}:6379")

    # Encryption key (reuse from cookie encryption)
    encryption_key: Optional[str] = None

    class Config:
        env_prefix = ""
        case_sensitive = False
        # Look for both UPPER_CASE and lower_case env vars
        env_file = ".env"
        extra = "ignore"


# Singleton instance
_settings: Optional[AdsSettings] = None


def get_ads_settings() -> AdsSettings:
    """Get the ads settings singleton."""
    global _settings
    if _settings is None:
        _settings = AdsSettings()
    return _settings


# Convenience function to check if platforms are configured
def is_meta_configured() -> bool:
    """Check if Meta Ads credentials are configured."""
    settings = get_ads_settings()
    return bool(settings.meta_app_id and settings.meta_app_secret)


def is_google_configured() -> bool:
    """Check if Google Ads credentials are configured."""
    settings = get_ads_settings()
    return bool(
        settings.google_client_id
        and settings.google_client_secret
        and settings.google_developer_token
    )
