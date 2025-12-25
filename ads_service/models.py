"""
Pydantic models for Ads Service API requests and responses.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, date
from enum import Enum


# =============================================================================
# Enums
# =============================================================================

class AdsPlatformType(str, Enum):
    META = "meta"
    GOOGLE = "google"


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"
    ERROR = "error"


class CampaignType(str, Enum):
    # Meta campaign types
    ADVANTAGE_PLUS = "advantage_plus"
    MANUAL = "manual"

    # Google campaign types
    PERFORMANCE_MAX = "performance_max"
    SEARCH = "search"
    DISPLAY = "display"


class CampaignObjective(str, Enum):
    CONVERSIONS = "conversions"
    TRAFFIC = "traffic"
    AWARENESS = "awareness"
    ENGAGEMENT = "engagement"
    LEADS = "leads"


# =============================================================================
# OAuth Models
# =============================================================================

class OAuthUrlResponse(BaseModel):
    """Response containing OAuth authorization URL."""
    url: str
    state: str
    platform: AdsPlatformType


class OAuthCallbackRequest(BaseModel):
    """OAuth callback parameters."""
    code: str
    state: str


# =============================================================================
# Platform Models
# =============================================================================

class AdsPlatformBase(BaseModel):
    """Base model for ads platform."""
    platform: AdsPlatformType
    account_id: Optional[str] = None
    account_name: Optional[str] = None


class AdsPlatformCreate(AdsPlatformBase):
    """Create a new ads platform connection."""
    access_token: str
    refresh_token: Optional[str] = None
    meta_page_id: Optional[str] = None
    meta_business_id: Optional[str] = None


class AdsPlatformResponse(AdsPlatformBase):
    """Response model for ads platform."""
    id: int
    is_connected: bool
    connection_error: Optional[str] = None
    created_at: datetime
    last_synced_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AdsPlatformListResponse(BaseModel):
    """List of connected platforms."""
    platforms: List[AdsPlatformResponse]
    meta_configured: bool
    google_configured: bool


# =============================================================================
# Campaign Models
# =============================================================================

class CampaignTargeting(BaseModel):
    """Campaign targeting configuration."""
    # Geographic targeting
    countries: Optional[List[str]] = None
    cities: Optional[List[str]] = None
    radius_miles: Optional[int] = None
    zip_codes: Optional[List[str]] = None

    # Demographic targeting
    age_min: Optional[int] = 18
    age_max: Optional[int] = 65
    genders: Optional[List[str]] = None  # ["male", "female", "all"]

    # Interest targeting (Meta)
    interests: Optional[List[str]] = None

    # Keywords (Google)
    keywords: Optional[List[str]] = None


class CampaignCreativeBase(BaseModel):
    """Campaign creative content."""
    headline: str = Field(..., max_length=255)
    description: Optional[str] = Field(None, max_length=500)
    destination_url: str = Field(..., max_length=500)
    media_url: Optional[str] = Field(None, max_length=500)
    call_to_action: Optional[str] = "LEARN_MORE"


class CampaignCreate(BaseModel):
    """Request to create a new campaign."""
    platform_id: int
    name: str = Field(..., max_length=255)
    campaign_type: CampaignType = CampaignType.ADVANTAGE_PLUS
    objective: CampaignObjective = CampaignObjective.CONVERSIONS

    # Budget (in cents)
    daily_budget_cents: int = Field(..., ge=100)  # Minimum $1/day
    lifetime_budget_cents: Optional[int] = None

    # Targeting
    targeting: CampaignTargeting = CampaignTargeting()

    # Creative
    creative: CampaignCreativeBase


class CampaignUpdate(BaseModel):
    """Request to update a campaign."""
    name: Optional[str] = Field(None, max_length=255)
    status: Optional[CampaignStatus] = None
    daily_budget_cents: Optional[int] = Field(None, ge=100)
    targeting: Optional[CampaignTargeting] = None


class CampaignResponse(BaseModel):
    """Response model for a campaign."""
    id: int
    platform_id: int
    platform: AdsPlatformType
    external_campaign_id: Optional[str] = None
    name: str
    campaign_type: Optional[str] = None
    objective: Optional[str] = None
    status: CampaignStatus
    daily_budget_cents: Optional[int] = None
    total_spend_cents: int = 0
    targeting: Optional[Dict[str, Any]] = None
    headline: Optional[str] = None
    description: Optional[str] = None
    destination_url: Optional[str] = None
    created_at: datetime
    last_synced_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CampaignListResponse(BaseModel):
    """List of campaigns."""
    campaigns: List[CampaignResponse]
    total: int


# =============================================================================
# Metrics Models
# =============================================================================

class MetricsSnapshot(BaseModel):
    """Daily metrics snapshot."""
    date: date
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    spend_cents: int = 0
    revenue_cents: int = 0
    ctr: Optional[float] = None
    cpc_cents: Optional[int] = None
    cpa_cents: Optional[int] = None
    roas: Optional[float] = None

    class Config:
        from_attributes = True


class CampaignMetricsResponse(BaseModel):
    """Campaign metrics with history."""
    campaign_id: int
    campaign_name: str
    platform: AdsPlatformType
    total_spend_cents: int
    total_revenue_cents: int
    total_impressions: int
    total_clicks: int
    total_conversions: int
    overall_roas: Optional[float] = None
    daily_metrics: List[MetricsSnapshot]


# =============================================================================
# Report Models
# =============================================================================

class WeeklyReportResponse(BaseModel):
    """Weekly performance report in plain language."""
    period_start: date
    period_end: date
    total_spend: float  # In dollars for display
    total_revenue: float
    new_customers: int
    impressions: int
    roas: Optional[float] = None
    best_platform: Optional[str] = None
    best_campaign: Optional[str] = None
    ai_insight: Optional[str] = None
    plain_language_summary: str


# =============================================================================
# Error Models
# =============================================================================

class AdsErrorResponse(BaseModel):
    """Error response."""
    error: str
    detail: Optional[str] = None
    platform: Optional[AdsPlatformType] = None
