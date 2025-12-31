"""
Work Integrations Services.

- OAuth manager: Handles OAuth2 flows for all platforms
- Activity aggregator: Scores and groups activities for digest
- Draft generator: Creates posts using Deep Agent
"""

from .oauth_manager import WorkOAuthManager, get_work_oauth_manager

__all__ = ["WorkOAuthManager", "get_work_oauth_manager"]
