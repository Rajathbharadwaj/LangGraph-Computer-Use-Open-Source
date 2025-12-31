"""
Work Integrations Services.

- OAuth manager: Handles OAuth2 flows for all platforms
- Activity aggregator: Scores and groups activities for digest
- Draft generator: Creates posts using Deep Agent
- Daily digest executor: Scheduled job for daily processing
"""

from .oauth_manager import WorkOAuthManager, get_work_oauth_manager
from .activity_aggregator import ActivityAggregator, get_activity_aggregator
from .draft_generator import DraftGenerator, get_draft_generator
from .daily_digest_executor import (
    DailyDigestExecutor,
    get_daily_digest_executor,
    shutdown_daily_digest_executor,
)

__all__ = [
    "WorkOAuthManager",
    "get_work_oauth_manager",
    "ActivityAggregator",
    "get_activity_aggregator",
    "DraftGenerator",
    "get_draft_generator",
    "DailyDigestExecutor",
    "get_daily_digest_executor",
    "shutdown_daily_digest_executor",
]
