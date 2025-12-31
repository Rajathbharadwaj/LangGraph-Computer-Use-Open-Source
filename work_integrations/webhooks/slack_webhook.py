"""
Slack Events API Webhook Handler.

Handles Slack events for:
- message: New messages in channels
- reaction_added: Reactions to messages
- app_mention: When the app is mentioned

Slack requires URL verification challenge handling.
"""

import logging
import hmac
import hashlib
import time
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models import WorkIntegration, WorkActivity
from ..config import (
    get_work_integrations_settings,
    ACTIVITY_SIGNIFICANCE,
    CATEGORY_MULTIPLIERS,
)

logger = logging.getLogger(__name__)


class SlackWebhookHandler:
    """
    Handler for Slack Events API.

    Validates request signatures and processes events
    into WorkActivity records.
    """

    def __init__(self):
        self.settings = get_work_integrations_settings()

    def verify_signature(
        self,
        body: bytes,
        timestamp: str,
        signature: str,
        signing_secret: str,
    ) -> bool:
        """
        Verify Slack request signature.

        Slack uses HMAC-SHA256 with the signing secret.

        Args:
            body: Raw request body
            timestamp: X-Slack-Request-Timestamp header
            signature: X-Slack-Signature header
            signing_secret: App signing secret

        Returns:
            True if signature is valid
        """
        # Check timestamp to prevent replay attacks
        current_time = time.time()
        if abs(current_time - int(timestamp)) > 60 * 5:
            logger.warning("Slack webhook timestamp too old")
            return False

        # Compute expected signature
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        expected_signature = (
            "v0="
            + hmac.new(
                signing_secret.encode(),
                sig_basestring.encode(),
                hashlib.sha256,
            ).hexdigest()
        )

        return hmac.compare_digest(expected_signature, signature)

    async def handle_event(
        self,
        payload: Dict[str, Any],
        db: AsyncSession,
    ) -> Optional[WorkActivity]:
        """
        Process a Slack event into a WorkActivity.

        Args:
            payload: Event payload from Slack
            db: Database session

        Returns:
            Created WorkActivity or None
        """
        # Handle URL verification challenge
        if payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge")}

        # Handle event callbacks
        if payload.get("type") != "event_callback":
            logger.debug(f"Ignoring Slack event type: {payload.get('type')}")
            return None

        event = payload.get("event", {})
        event_type = event.get("type")
        team_id = payload.get("team_id")

        logger.info(f"Processing Slack event: {event_type} from team {team_id}")

        # Find the integration
        result = await db.execute(
            select(WorkIntegration).where(
                WorkIntegration.platform == "slack",
                WorkIntegration.external_account_id == team_id,
                WorkIntegration.is_active == True,
            )
        )
        integration = result.scalar_one_or_none()

        if not integration:
            logger.warning(f"No active Slack integration found for team {team_id}")
            return None

        # Route to specific handler
        handler_map = {
            "message": self._handle_message,
            "reaction_added": self._handle_reaction,
            "app_mention": self._handle_mention,
        }

        handler = handler_map.get(event_type)
        if not handler:
            logger.debug(f"No handler for Slack event type: {event_type}")
            return None

        return await handler(event, integration, db)

    async def _handle_message(
        self,
        event: Dict[str, Any],
        integration: WorkIntegration,
        db: AsyncSession,
    ) -> Optional[WorkActivity]:
        """Handle message event."""
        # Skip bot messages
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return None

        # Skip message edits, deletes
        if event.get("subtype") in ["message_changed", "message_deleted"]:
            return None

        user_id = event.get("user")
        channel_id = event.get("channel")
        text = event.get("text", "")
        ts = event.get("ts")

        # Skip empty messages
        if not text or len(text) < 10:
            return None

        # Check if channel is being tracked
        tracked_channels = integration.slack_channels or []
        if tracked_channels and channel_id not in tracked_channels:
            return None

        # Calculate significance
        base_score = ACTIVITY_SIGNIFICANCE.get("comment_added", 0.2)
        category = "collaboration"
        multiplier = CATEGORY_MULTIPLIERS.get(category, 1.0)

        # Bonus for longer, more substantive messages
        word_count = len(text.split())
        length_bonus = min(word_count * 0.01, 0.2)

        significance = base_score * multiplier + length_bonus

        # Create activity
        activity = WorkActivity(
            integration_id=integration.id,
            user_id=integration.user_id,
            platform="slack",
            activity_type="message_sent",
            category=category,
            title=f"Sent message in channel",
            description=text[:500] if len(text) > 500 else text,
            url=None,  # Slack message links require workspace info
            repo_or_project=channel_id,
            significance_score=significance,
            metadata={
                "channel_id": channel_id,
                "user_id": user_id,
                "thread_ts": event.get("thread_ts"),
                "ts": ts,
                "has_attachments": bool(event.get("attachments")),
                "has_files": bool(event.get("files")),
            },
            activity_at=datetime.utcfromtimestamp(float(ts)),
        )

        db.add(activity)
        await db.commit()
        await db.refresh(activity)

        logger.info(f"Created Slack message activity: {activity.id}")
        return activity

    async def _handle_reaction(
        self,
        event: Dict[str, Any],
        integration: WorkIntegration,
        db: AsyncSession,
    ) -> Optional[WorkActivity]:
        """Handle reaction_added event."""
        user_id = event.get("user")
        reaction = event.get("reaction")
        item = event.get("item", {})

        channel_id = item.get("channel")
        ts = item.get("ts")

        # Check if channel is being tracked
        tracked_channels = integration.slack_channels or []
        if tracked_channels and channel_id not in tracked_channels:
            return None

        # Simple significance for reactions
        base_score = ACTIVITY_SIGNIFICANCE.get("comment_added", 0.2) * 0.5
        category = "collaboration"
        multiplier = CATEGORY_MULTIPLIERS.get(category, 1.0)

        significance = base_score * multiplier

        # Create activity
        activity = WorkActivity(
            integration_id=integration.id,
            user_id=integration.user_id,
            platform="slack",
            activity_type="reaction_added",
            category=category,
            title=f"Added :{reaction}: reaction",
            description=f"Reacted with :{reaction}: to a message",
            repo_or_project=channel_id,
            significance_score=significance,
            metadata={
                "channel_id": channel_id,
                "reaction": reaction,
                "item_ts": ts,
                "user_id": user_id,
            },
            activity_at=datetime.utcnow(),
        )

        db.add(activity)
        await db.commit()
        await db.refresh(activity)

        logger.info(f"Created Slack reaction activity: {activity.id}")
        return activity

    async def _handle_mention(
        self,
        event: Dict[str, Any],
        integration: WorkIntegration,
        db: AsyncSession,
    ) -> Optional[WorkActivity]:
        """Handle app_mention event."""
        # App mentions are typically recorded as message activities
        # But we could track them separately if needed
        return None


# Singleton instance
_handler: Optional[SlackWebhookHandler] = None


def get_slack_webhook_handler() -> SlackWebhookHandler:
    """Get or create the Slack webhook handler."""
    global _handler
    if _handler is None:
        _handler = SlackWebhookHandler()
    return _handler
