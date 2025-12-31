"""
Configuration for Work Integrations.

Loads OAuth credentials and settings from environment variables.
"""

import os
from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import Optional


class WorkIntegrationsSettings(BaseSettings):
    """Work integrations configuration from environment."""

    # Redis for OAuth state
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    # Base URLs
    frontend_url: str = os.getenv("FRONTEND_URL", "https://app.paralleluniverse.ai")
    backend_url: str = os.getenv("BACKEND_URL", "https://backend-websocket-server-644185288504.us-central1.run.app")

    # =========================================================================
    # GitHub OAuth
    # Scopes: repo, read:user, user:email
    # https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps
    # =========================================================================
    github_client_id: str = os.getenv("GITHUB_CLIENT_ID", "")
    github_client_secret: str = os.getenv("GITHUB_CLIENT_SECRET", "")
    github_redirect_uri: str = os.getenv(
        "GITHUB_REDIRECT_URI",
        f"{os.getenv('BACKEND_URL', 'https://backend-websocket-server-644185288504.us-central1.run.app')}/api/work-integrations/oauth/github/callback"
    )
    github_webhook_secret: str = os.getenv("GITHUB_WEBHOOK_SECRET", "")  # For verifying webhooks

    # =========================================================================
    # Slack OAuth
    # Scopes: channels:history, channels:read, users:read
    # https://api.slack.com/authentication/oauth-v2
    # =========================================================================
    slack_client_id: str = os.getenv("SLACK_CLIENT_ID", "")
    slack_client_secret: str = os.getenv("SLACK_CLIENT_SECRET", "")
    slack_redirect_uri: str = os.getenv(
        "SLACK_REDIRECT_URI",
        f"{os.getenv('BACKEND_URL', 'https://backend-websocket-server-644185288504.us-central1.run.app')}/api/work-integrations/oauth/slack/callback"
    )
    slack_signing_secret: str = os.getenv("SLACK_SIGNING_SECRET", "")

    # =========================================================================
    # Notion OAuth
    # https://developers.notion.com/docs/authorization
    # =========================================================================
    notion_client_id: str = os.getenv("NOTION_CLIENT_ID", "")
    notion_client_secret: str = os.getenv("NOTION_CLIENT_SECRET", "")
    notion_redirect_uri: str = os.getenv(
        "NOTION_REDIRECT_URI",
        f"{os.getenv('BACKEND_URL', 'https://backend-websocket-server-644185288504.us-central1.run.app')}/api/work-integrations/oauth/notion/callback"
    )

    # =========================================================================
    # Linear OAuth
    # https://developers.linear.app/docs/oauth/authentication
    # =========================================================================
    linear_client_id: str = os.getenv("LINEAR_CLIENT_ID", "")
    linear_client_secret: str = os.getenv("LINEAR_CLIENT_SECRET", "")
    linear_redirect_uri: str = os.getenv(
        "LINEAR_REDIRECT_URI",
        f"{os.getenv('BACKEND_URL', 'https://backend-websocket-server-644185288504.us-central1.run.app')}/api/work-integrations/oauth/linear/callback"
    )

    # =========================================================================
    # Figma OAuth
    # https://www.figma.com/developers/api#oauth2
    # =========================================================================
    figma_client_id: str = os.getenv("FIGMA_CLIENT_ID", "")
    figma_client_secret: str = os.getenv("FIGMA_CLIENT_SECRET", "")
    figma_redirect_uri: str = os.getenv(
        "FIGMA_REDIRECT_URI",
        f"{os.getenv('BACKEND_URL', 'https://backend-websocket-server-644185288504.us-central1.run.app')}/api/work-integrations/oauth/figma/callback"
    )

    # =========================================================================
    # Activity Processing
    # =========================================================================
    daily_digest_hour: int = int(os.getenv("DAILY_DIGEST_HOUR", "21"))  # 9 PM
    draft_expiration_days: int = int(os.getenv("DRAFT_EXPIRATION_DAYS", "7"))

    class Config:
        env_file = ".env"


@lru_cache()
def get_work_integrations_settings() -> WorkIntegrationsSettings:
    """Get cached settings instance."""
    return WorkIntegrationsSettings()


# Platform-specific OAuth scopes
PLATFORM_SCOPES = {
    "github": ["repo", "read:user", "user:email"],
    "slack": ["channels:history", "channels:read", "users:read", "chat:write"],
    "notion": [],  # Notion uses OAuth with internal integration
    "linear": ["read", "write", "issues:create"],
    "figma": ["file_read"],
}

# Activity types per platform
ACTIVITY_TYPES = {
    "github": [
        "commit_pushed",
        "pr_opened",
        "pr_merged",
        "pr_closed",
        "release_published",
        "issue_opened",
        "issue_closed",
        "review_submitted",
    ],
    "slack": [
        "message_sent",
        "reaction_added",
    ],
    "notion": [
        "page_created",
        "page_updated",
        "database_entry_created",
    ],
    "linear": [
        "issue_created",
        "issue_completed",
        "project_updated",
        "cycle_completed",
    ],
    "figma": [
        "comment_added",
        "version_created",
        "file_updated",
    ],
}

# Activity significance base scores (0.0 - 1.0)
SIGNIFICANCE_SCORES = {
    # GitHub - code shipping is most significant
    "release_published": 1.0,
    "pr_merged": 0.8,
    "pr_opened": 0.4,
    "issue_closed": 0.5,
    "commit_pushed": 0.3,
    "review_submitted": 0.3,
    "issue_opened": 0.3,

    # Linear - similar to GitHub issues
    "cycle_completed": 0.9,
    "issue_completed": 0.6,
    "project_updated": 0.4,
    "issue_created": 0.3,

    # Slack - collaboration signals
    "message_sent": 0.2,
    "reaction_added": 0.1,

    # Notion - documentation
    "page_created": 0.4,
    "page_updated": 0.3,
    "database_entry_created": 0.3,

    # Figma - design work
    "version_created": 0.6,
    "file_updated": 0.3,
    "comment_added": 0.2,
}

# Category multipliers
CATEGORY_MULTIPLIERS = {
    "code_shipped": 1.5,
    "progress": 1.0,
    "collaboration": 0.8,
}

# Credits per integration per month
INTEGRATION_CREDITS = {
    "github": 100,
    "slack": 100,
    "notion": 100,
    "linear": 100,
    "figma": 100,
}

# Plan limits for work integrations
PLAN_INTEGRATION_LIMITS = {
    "free": 0,
    "starter": 1,
    "pro": 3,
    "pro_plus": 5,
    "ultimate": -1,  # Unlimited
}
