"""
Pydantic models for Work Integrations API.

Request/response schemas for OAuth, integrations, activities, and drafts.
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


# =============================================================================
# Enums
# =============================================================================

class WorkPlatform(str, Enum):
    """Supported work platforms."""
    GITHUB = "github"
    SLACK = "slack"
    NOTION = "notion"
    LINEAR = "linear"
    FIGMA = "figma"


class ActivityCategory(str, Enum):
    """Activity categories for grouping."""
    CODE_SHIPPED = "code_shipped"
    PROGRESS = "progress"
    COLLABORATION = "collaboration"


class DraftStatus(str, Enum):
    """Activity draft status."""
    PENDING = "pending"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SCHEDULED = "scheduled"
    POSTED = "posted"


# =============================================================================
# OAuth Models
# =============================================================================

class OAuthURLResponse(BaseModel):
    """Response for OAuth URL generation."""
    url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    """OAuth callback parameters."""
    code: str
    state: str


# =============================================================================
# Integration Models
# =============================================================================

class IntegrationBase(BaseModel):
    """Base integration fields."""
    platform: WorkPlatform
    external_account_name: Optional[str] = None
    is_active: bool = True


class IntegrationCreate(IntegrationBase):
    """Request to create integration (after OAuth)."""
    pass


class IntegrationSettings(BaseModel):
    """Settings for an integration."""
    # GitHub
    github_repos: Optional[List[str]] = None
    github_org: Optional[str] = None

    # Slack
    slack_channels: Optional[List[str]] = None

    # Notion
    notion_database_ids: Optional[List[str]] = None

    # Linear
    linear_team_id: Optional[str] = None

    # Figma
    figma_project_ids: Optional[List[str]] = None

    # Capture settings
    capture_commits: Optional[bool] = None
    capture_prs: Optional[bool] = None
    capture_releases: Optional[bool] = None
    capture_issues: Optional[bool] = None
    capture_comments: Optional[bool] = None


class IntegrationResponse(IntegrationBase):
    """Full integration response."""
    id: int
    user_id: str
    external_account_id: Optional[str] = None
    is_connected: bool = True
    connection_error: Optional[str] = None
    webhook_registered: bool = False

    # Platform-specific settings
    github_repos: List[str] = []
    github_org: Optional[str] = None
    slack_channels: List[str] = []
    notion_database_ids: List[str] = []
    linear_team_id: Optional[str] = None
    figma_project_ids: List[str] = []

    # Capture settings
    capture_commits: bool = True
    capture_prs: bool = True
    capture_releases: bool = True
    capture_issues: bool = True
    capture_comments: bool = True

    # Timestamps
    created_at: datetime
    last_synced_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class IntegrationListResponse(BaseModel):
    """List of integrations."""
    integrations: List[IntegrationResponse]
    total: int


# =============================================================================
# Activity Models
# =============================================================================

class ActivityBase(BaseModel):
    """Base activity fields."""
    platform: WorkPlatform
    activity_type: str
    category: ActivityCategory
    title: str
    description: Optional[str] = None
    url: Optional[str] = None
    repo_or_project: Optional[str] = None


class ActivityResponse(ActivityBase):
    """Full activity response."""
    id: int
    integration_id: int
    external_id: Optional[str] = None

    # Metrics
    lines_added: int = 0
    lines_removed: int = 0
    files_changed: int = 0
    comments_count: int = 0
    reactions_count: int = 0
    significance_score: float = 0.0

    # Processing
    processed: bool = False
    draft_id: Optional[int] = None

    # Timestamps
    activity_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class ActivityListResponse(BaseModel):
    """List of activities with pagination."""
    activities: List[ActivityResponse]
    total: int
    page: int = 1
    page_size: int = 50


class ActivityFilters(BaseModel):
    """Filters for activity queries."""
    platform: Optional[WorkPlatform] = None
    category: Optional[ActivityCategory] = None
    activity_type: Optional[str] = None
    processed: Optional[bool] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    min_significance: Optional[float] = None


# =============================================================================
# Draft Models
# =============================================================================

class DraftBase(BaseModel):
    """Base draft fields."""
    content: str
    digest_date: date
    digest_theme: Optional[str] = None


class DraftCreate(DraftBase):
    """Request to create draft manually (for testing)."""
    source_activity_ids: List[int] = []


class DraftResponse(DraftBase):
    """Full draft response."""
    id: int
    user_id: str
    x_account_id: int
    status: DraftStatus = DraftStatus.PENDING

    # AI metadata
    ai_rationale: Optional[str] = None
    activity_summary: Optional[str] = None
    source_activity_ids: List[int] = []

    # User edits
    user_edited_content: Optional[str] = None

    # Scheduling
    scheduled_post_id: Optional[int] = None
    scheduled_at: Optional[datetime] = None
    posted_at: Optional[datetime] = None

    # Expiration
    expires_at: Optional[datetime] = None

    # Feedback
    feedback_rating: Optional[int] = None
    feedback_text: Optional[str] = None

    # Timestamps
    created_at: datetime
    updated_at: datetime
    reviewed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DraftListResponse(BaseModel):
    """List of drafts."""
    drafts: List[DraftResponse]
    total: int
    pending_count: int = 0


class DraftApproveRequest(BaseModel):
    """Request to approve a draft."""
    edited_content: Optional[str] = None  # If user edited before approving
    schedule_at: Optional[datetime] = None  # Optional specific time


class DraftRejectRequest(BaseModel):
    """Request to reject a draft."""
    reason: Optional[str] = None
    feedback_rating: Optional[int] = Field(None, ge=1, le=5)


class DraftFeedbackRequest(BaseModel):
    """Request to provide feedback on a draft."""
    rating: int = Field(..., ge=1, le=5)
    feedback_text: Optional[str] = None


# =============================================================================
# GitHub-specific Models
# =============================================================================

class GitHubRepo(BaseModel):
    """GitHub repository info."""
    id: int
    name: str
    full_name: str
    private: bool
    description: Optional[str] = None
    html_url: str
    default_branch: str = "main"


class GitHubRepoListResponse(BaseModel):
    """List of GitHub repositories."""
    repos: List[GitHubRepo]
    total: int


class GitHubWebhookPayload(BaseModel):
    """GitHub webhook event payload (simplified)."""
    action: Optional[str] = None
    repository: Optional[Dict[str, Any]] = None
    sender: Optional[Dict[str, Any]] = None
    # Event-specific fields are validated elsewhere


# =============================================================================
# Webhook Models
# =============================================================================

class WebhookResponse(BaseModel):
    """Response after processing webhook."""
    success: bool
    message: str
    activities_created: int = 0


# =============================================================================
# Stats Models
# =============================================================================

class IntegrationStats(BaseModel):
    """Statistics for an integration."""
    integration_id: int
    platform: WorkPlatform
    total_activities: int = 0
    activities_today: int = 0
    activities_this_week: int = 0
    last_activity_at: Optional[datetime] = None
    drafts_generated: int = 0
    drafts_approved: int = 0


class WorkIntegrationsOverview(BaseModel):
    """Overview stats for all work integrations."""
    total_integrations: int = 0
    active_integrations: int = 0
    total_activities_captured: int = 0
    pending_drafts: int = 0
    drafts_approved_this_month: int = 0
    platforms_connected: List[WorkPlatform] = []
