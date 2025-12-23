"""
Ads Agent Package

Contains the Ads Deep Agent for natural language ad campaign creation.
Supports Meta (Facebook/Instagram) and Google Ads platforms.
"""

from .memory import AdsUserMemory, BusinessPreferences
from .subagents import get_ads_atomic_subagents
from .tools import (
    create_meta_campaign_tool,
    create_google_campaign_tool,
    publish_campaign_tool,
    activate_campaign_tool,
    get_user_platforms_tool,
    get_user_campaigns_tool,
)

__all__ = [
    "AdsUserMemory",
    "BusinessPreferences",
    "get_ads_atomic_subagents",
    "create_meta_campaign_tool",
    "create_google_campaign_tool",
    "publish_campaign_tool",
    "activate_campaign_tool",
    "get_user_platforms_tool",
    "get_user_campaigns_tool",
]
