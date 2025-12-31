"""
Linear Webhook Handler.

Handles Linear webhooks for:
- Issue: create, update, remove
- Comment: create, update
- Project: update
- Cycle: update

Linear webhooks include a signature for verification.
"""

import logging
import hmac
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models import WorkIntegration, WorkActivity
from ..config import (
    ACTIVITY_SIGNIFICANCE,
    CATEGORY_MULTIPLIERS,
)

logger = logging.getLogger(__name__)


class LinearWebhookHandler:
    """
    Handler for Linear webhooks.

    Validates webhook signatures and processes events
    into WorkActivity records.
    """

    def verify_signature(
        self,
        body: bytes,
        signature: str,
        webhook_secret: str,
    ) -> bool:
        """
        Verify Linear webhook signature.

        Linear uses HMAC-SHA256 with the webhook secret.

        Args:
            body: Raw request body
            signature: Linear-Signature header
            webhook_secret: Integration webhook secret

        Returns:
            True if signature is valid
        """
        expected_signature = hmac.new(
            webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected_signature, signature)

    async def handle_event(
        self,
        payload: Dict[str, Any],
        db: AsyncSession,
    ) -> Optional[WorkActivity]:
        """
        Process a Linear webhook event into a WorkActivity.

        Args:
            payload: Webhook payload from Linear
            db: Database session

        Returns:
            Created WorkActivity or None
        """
        action = payload.get("action")
        event_type = payload.get("type")
        data = payload.get("data", {})
        organization_id = payload.get("organizationId")

        logger.info(f"Processing Linear webhook: {event_type}.{action}")

        # Find the integration by organization
        result = await db.execute(
            select(WorkIntegration).where(
                WorkIntegration.platform == "linear",
                WorkIntegration.external_account_id == organization_id,
                WorkIntegration.is_active == True,
            )
        )
        integration = result.scalar_one_or_none()

        if not integration:
            logger.warning(f"No active Linear integration for org {organization_id}")
            return None

        # Route to specific handler
        handler_map = {
            "Issue": self._handle_issue,
            "Comment": self._handle_comment,
            "Project": self._handle_project,
            "Cycle": self._handle_cycle,
        }

        handler = handler_map.get(event_type)
        if not handler:
            logger.debug(f"No handler for Linear type: {event_type}")
            return None

        return await handler(action, data, integration, db)

    async def _handle_issue(
        self,
        action: str,
        data: Dict[str, Any],
        integration: WorkIntegration,
        db: AsyncSession,
    ) -> Optional[WorkActivity]:
        """Handle Issue events."""
        issue_id = data.get("id")
        identifier = data.get("identifier", "")
        title = data.get("title", "")
        description = data.get("description", "")
        url = data.get("url", "")
        state = data.get("state", {})
        state_name = state.get("name", "")
        state_type = state.get("type", "")
        project = data.get("project", {})
        project_name = project.get("name", "") if project else ""
        priority = data.get("priority", 0)
        labels = data.get("labels", {}).get("nodes", [])

        # Determine activity type and category
        if action == "create":
            activity_type = "issue_opened"
            activity_title = f"Created issue: {identifier}"
            category = "progress"
            base_score = ACTIVITY_SIGNIFICANCE.get("issue_opened", 0.3)

        elif action == "update":
            # Check if this is a state change to completed
            if state_type in ["completed", "done"]:
                activity_type = "issue_closed"
                activity_title = f"Closed issue: {identifier}"
                category = "code_shipped"
                base_score = ACTIVITY_SIGNIFICANCE.get("issue_closed", 0.5)
            else:
                # Just an update, lower significance
                activity_type = "issue_updated"
                activity_title = f"Updated issue: {identifier}"
                category = "progress"
                base_score = ACTIVITY_SIGNIFICANCE.get("comment_added", 0.2) * 0.5

        elif action == "remove":
            # Deleted issues - skip or low significance
            return None

        else:
            logger.debug(f"Ignoring Linear issue action: {action}")
            return None

        # Calculate significance
        multiplier = CATEGORY_MULTIPLIERS.get(category, 1.0)

        # Priority bonus (1=Urgent, 2=High, 3=Normal, 4=Low)
        priority_bonus = max(0, (4 - priority) * 0.05) if priority > 0 else 0

        # Label bonus (more labels = more complex)
        label_bonus = min(len(labels) * 0.02, 0.1)

        significance = base_score * multiplier + priority_bonus + label_bonus

        # Create activity
        activity = WorkActivity(
            integration_id=integration.id,
            user_id=integration.user_id,
            platform="linear",
            activity_type=activity_type,
            category=category,
            title=activity_title,
            description=f"{title}\n\n{description[:500]}" if description else title,
            url=url,
            repo_or_project=project_name,
            significance_score=significance,
            metadata={
                "issue_id": issue_id,
                "identifier": identifier,
                "state": state_name,
                "state_type": state_type,
                "priority": priority,
                "labels": [l.get("name") for l in labels],
            },
            activity_at=datetime.utcnow(),
        )

        db.add(activity)
        await db.commit()
        await db.refresh(activity)

        logger.info(f"Created Linear issue activity: {activity.id}")
        return activity

    async def _handle_comment(
        self,
        action: str,
        data: Dict[str, Any],
        integration: WorkIntegration,
        db: AsyncSession,
    ) -> Optional[WorkActivity]:
        """Handle Comment events."""
        if action != "create":
            return None

        body = data.get("body", "")
        issue = data.get("issue", {})
        issue_identifier = issue.get("identifier", "")
        issue_title = issue.get("title", "")
        url = data.get("url", "")

        # Calculate significance
        base_score = ACTIVITY_SIGNIFICANCE.get("comment_added", 0.2)
        category = "collaboration"
        multiplier = CATEGORY_MULTIPLIERS.get(category, 1.0)

        # Length bonus for substantive comments
        word_count = len(body.split())
        length_bonus = min(word_count * 0.01, 0.15)

        significance = base_score * multiplier + length_bonus

        # Create activity
        activity = WorkActivity(
            integration_id=integration.id,
            user_id=integration.user_id,
            platform="linear",
            activity_type="comment_added",
            category=category,
            title=f"Commented on {issue_identifier}",
            description=body[:500] if len(body) > 500 else body,
            url=url,
            repo_or_project=issue_title,
            significance_score=significance,
            metadata={
                "issue_identifier": issue_identifier,
                "issue_title": issue_title,
                "comment_length": len(body),
            },
            activity_at=datetime.utcnow(),
        )

        db.add(activity)
        await db.commit()
        await db.refresh(activity)

        logger.info(f"Created Linear comment activity: {activity.id}")
        return activity

    async def _handle_project(
        self,
        action: str,
        data: Dict[str, Any],
        integration: WorkIntegration,
        db: AsyncSession,
    ) -> Optional[WorkActivity]:
        """Handle Project events."""
        if action != "update":
            return None

        name = data.get("name", "")
        state = data.get("state", "")
        progress = data.get("progress", 0)
        url = data.get("url", "")

        # Only track significant project updates (state changes, completion)
        if state not in ["completed", "started"]:
            return None

        if state == "completed":
            activity_type = "project_completed"
            activity_title = f"Completed project: {name}"
            category = "code_shipped"
            base_score = ACTIVITY_SIGNIFICANCE.get("release_published", 1.0) * 0.8
        else:
            activity_type = "project_started"
            activity_title = f"Started project: {name}"
            category = "progress"
            base_score = ACTIVITY_SIGNIFICANCE.get("pr_opened", 0.4)

        multiplier = CATEGORY_MULTIPLIERS.get(category, 1.0)
        significance = base_score * multiplier

        # Create activity
        activity = WorkActivity(
            integration_id=integration.id,
            user_id=integration.user_id,
            platform="linear",
            activity_type=activity_type,
            category=category,
            title=activity_title,
            description=f"Project: {name} (Progress: {int(progress * 100)}%)",
            url=url,
            repo_or_project=name,
            significance_score=significance,
            metadata={
                "project_name": name,
                "state": state,
                "progress": progress,
            },
            activity_at=datetime.utcnow(),
        )

        db.add(activity)
        await db.commit()
        await db.refresh(activity)

        logger.info(f"Created Linear project activity: {activity.id}")
        return activity

    async def _handle_cycle(
        self,
        action: str,
        data: Dict[str, Any],
        integration: WorkIntegration,
        db: AsyncSession,
    ) -> Optional[WorkActivity]:
        """Handle Cycle events (sprints)."""
        if action != "update":
            return None

        name = data.get("name", "")
        number = data.get("number", 0)
        progress = data.get("progress", 0)
        completed_at = data.get("completedAt")

        # Only track cycle completions
        if not completed_at:
            return None

        base_score = ACTIVITY_SIGNIFICANCE.get("release_published", 1.0) * 0.6
        category = "code_shipped"
        multiplier = CATEGORY_MULTIPLIERS.get(category, 1.0)
        significance = base_score * multiplier

        # Create activity
        activity = WorkActivity(
            integration_id=integration.id,
            user_id=integration.user_id,
            platform="linear",
            activity_type="cycle_completed",
            category=category,
            title=f"Completed sprint: {name or f'Cycle {number}'}",
            description=f"Sprint {number} completed with {int(progress * 100)}% progress",
            repo_or_project=name or f"Cycle {number}",
            significance_score=significance,
            metadata={
                "cycle_number": number,
                "name": name,
                "progress": progress,
            },
            activity_at=datetime.utcnow(),
        )

        db.add(activity)
        await db.commit()
        await db.refresh(activity)

        logger.info(f"Created Linear cycle activity: {activity.id}")
        return activity


# Singleton instance
_handler: Optional[LinearWebhookHandler] = None


def get_linear_webhook_handler() -> LinearWebhookHandler:
    """Get or create the Linear webhook handler."""
    global _handler
    if _handler is None:
        _handler = LinearWebhookHandler()
    return _handler
