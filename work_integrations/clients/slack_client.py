"""
Slack API Client for Work Integrations.

Handles Slack Web API calls for:
- Listing channels
- Fetching messages and reactions
- User information
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import httpx

from ..config import get_work_integrations_settings

logger = logging.getLogger(__name__)

SLACK_API_BASE = "https://slack.com/api"


class SlackClient:
    """
    Slack Web API client for work integrations.

    Uses OAuth tokens to access workspace data.
    """

    def __init__(self, access_token: str):
        """Initialize with access token."""
        self.access_token = access_token
        self.settings = get_work_integrations_settings()
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """Make a request to Slack API."""
        url = f"{SLACK_API_BASE}/{endpoint}"
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                url,
                headers=self._headers,
                **kwargs,
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("ok"):
                raise Exception(f"Slack API error: {data.get('error')}")

            return data

    # =========================================================================
    # Auth & User Info
    # =========================================================================

    async def test_auth(self) -> Dict[str, Any]:
        """Test authentication and get user/team info."""
        return await self._request("GET", "auth.test")

    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Get information about a user."""
        data = await self._request("GET", "users.info", params={"user": user_id})
        return data.get("user", {})

    # =========================================================================
    # Channels
    # =========================================================================

    async def list_channels(
        self,
        types: str = "public_channel,private_channel",
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        List channels the bot has access to.

        Args:
            types: Channel types to include
            limit: Maximum channels to return

        Returns:
            List of channel objects
        """
        channels = []
        cursor = None

        while True:
            params = {
                "types": types,
                "limit": min(limit, 200),
                "exclude_archived": True,
            }
            if cursor:
                params["cursor"] = cursor

            data = await self._request("GET", "conversations.list", params=params)
            channels.extend(data.get("channels", []))

            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor or len(channels) >= limit:
                break

        return channels[:limit]

    async def get_channel_info(self, channel_id: str) -> Dict[str, Any]:
        """Get information about a channel."""
        data = await self._request(
            "GET",
            "conversations.info",
            params={"channel": channel_id},
        )
        return data.get("channel", {})

    # =========================================================================
    # Messages
    # =========================================================================

    async def get_channel_history(
        self,
        channel_id: str,
        oldest: datetime = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get message history for a channel.

        Args:
            channel_id: Channel ID
            oldest: Only messages after this timestamp
            limit: Maximum messages to return

        Returns:
            List of message objects
        """
        params = {
            "channel": channel_id,
            "limit": min(limit, 200),
        }
        if oldest:
            params["oldest"] = str(oldest.timestamp())

        data = await self._request("GET", "conversations.history", params=params)
        return data.get("messages", [])

    async def get_thread_replies(
        self,
        channel_id: str,
        thread_ts: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get replies to a thread."""
        params = {
            "channel": channel_id,
            "ts": thread_ts,
            "limit": min(limit, 200),
        }

        data = await self._request("GET", "conversations.replies", params=params)
        return data.get("messages", [])

    # =========================================================================
    # Reactions
    # =========================================================================

    async def get_reactions(
        self,
        channel_id: str,
        timestamp: str,
    ) -> List[Dict[str, Any]]:
        """Get reactions on a message."""
        data = await self._request(
            "GET",
            "reactions.get",
            params={
                "channel": channel_id,
                "timestamp": timestamp,
            },
        )
        message = data.get("message", {})
        return message.get("reactions", [])

    # =========================================================================
    # User Activity
    # =========================================================================

    async def get_user_messages(
        self,
        user_id: str,
        channel_ids: List[str],
        since: datetime = None,
    ) -> List[Dict[str, Any]]:
        """
        Get messages from a specific user across channels.

        Note: Slack doesn't have a direct API for this, so we need to
        search or iterate through channels.
        """
        if since is None:
            since = datetime.utcnow() - timedelta(days=1)

        messages = []

        for channel_id in channel_ids[:10]:  # Limit to avoid rate limits
            try:
                history = await self.get_channel_history(
                    channel_id,
                    oldest=since,
                    limit=50,
                )

                # Filter to user's messages
                user_messages = [
                    {**msg, "channel_id": channel_id}
                    for msg in history
                    if msg.get("user") == user_id
                ]
                messages.extend(user_messages)

            except Exception as e:
                logger.warning(f"Failed to get history for channel {channel_id}: {e}")
                continue

        return messages


def get_slack_client(access_token: str) -> SlackClient:
    """Create a Slack client with the given access token."""
    return SlackClient(access_token)
