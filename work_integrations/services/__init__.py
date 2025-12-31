"""
Work Integrations Services.

- OAuth manager: Handles OAuth2 flows for all platforms
- Activity aggregator: Scores and groups activities for digest
- Draft generator: Creates posts using Deep Agent
- Daily digest executor: Scheduled job for daily processing
- Polling service: Polls Notion/Figma for changes (no webhook support)
"""

from .oauth_manager import WorkOAuthManager, get_work_oauth_manager
from .activity_aggregator import ActivityAggregator, get_activity_aggregator
from .draft_generator import DraftGenerator, get_draft_generator
from .daily_digest_executor import (
    DailyDigestExecutor,
    get_daily_digest_executor,
    shutdown_daily_digest_executor,
)
from .polling_service import (
    PollingService,
    get_polling_service,
    start_polling_service,
)

__all__ = [
    # OAuth
    "WorkOAuthManager",
    "get_work_oauth_manager",
    # Aggregation
    "ActivityAggregator",
    "get_activity_aggregator",
    # Draft Generation
    "DraftGenerator",
    "get_draft_generator",
    # Daily Digest
    "DailyDigestExecutor",
    "get_daily_digest_executor",
    "shutdown_daily_digest_executor",
    # Polling (for Notion/Figma)
    "PollingService",
    "get_polling_service",
    "start_polling_service",
]
