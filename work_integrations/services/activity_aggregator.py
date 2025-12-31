"""
Activity Aggregator Service for Work Integrations.

Aggregates daily work activities, scores by significance,
groups by theme/project, and prepares for draft generation.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, date
from collections import defaultdict
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import WorkActivity, WorkIntegration, XAccount
from ..config import SIGNIFICANCE_SCORES, CATEGORY_MULTIPLIERS
from ..models import WorkPlatform, ActivityCategory

logger = logging.getLogger(__name__)


# Theme detection keywords
THEME_KEYWORDS = {
    "shipping": ["release", "deploy", "launch", "ship", "publish", "production", "live"],
    "building": ["implement", "add", "create", "build", "develop", "feature"],
    "fixing": ["fix", "bug", "issue", "resolve", "patch", "hotfix", "error"],
    "improving": ["refactor", "optimize", "improve", "enhance", "update", "upgrade"],
    "collaborating": ["review", "comment", "discuss", "feedback", "merge", "approve"],
    "learning": ["learn", "study", "research", "explore", "experiment", "try"],
    "documenting": ["doc", "readme", "guide", "tutorial", "example"],
}


class ActivityAggregator:
    """
    Aggregates work activities for daily digest generation.

    Responsibilities:
    - Query unprocessed activities from the past 24 hours
    - Score activities by significance
    - Group activities by theme/project
    - Select top activities for draft generation
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_daily_activities(
        self,
        user_id: str,
        target_date: date = None,
    ) -> List[WorkActivity]:
        """
        Get all unprocessed activities for a user on a given date.

        Args:
            user_id: User ID
            target_date: Date to aggregate (defaults to today)

        Returns:
            List of WorkActivity records
        """
        if target_date is None:
            target_date = datetime.utcnow().date()

        start = datetime.combine(target_date, datetime.min.time())
        end = datetime.combine(target_date, datetime.max.time())

        result = await self.db.execute(
            select(WorkActivity)
            .join(WorkIntegration)
            .where(
                and_(
                    WorkActivity.user_id == user_id,
                    WorkActivity.activity_at >= start,
                    WorkActivity.activity_at <= end,
                    WorkActivity.processed == False,
                    WorkIntegration.is_active == True,
                )
            )
            .order_by(WorkActivity.significance_score.desc())
        )

        return list(result.scalars().all())

    def detect_theme(self, activities: List[WorkActivity]) -> str:
        """
        Detect the primary theme from a list of activities.

        Analyzes titles and descriptions to find common themes.
        """
        theme_scores = defaultdict(float)

        for activity in activities:
            text = f"{activity.title} {activity.description or ''}".lower()

            for theme, keywords in THEME_KEYWORDS.items():
                for keyword in keywords:
                    if keyword in text:
                        # Weight by significance score
                        theme_scores[theme] += activity.significance_score

        if not theme_scores:
            return "building"  # Default theme

        return max(theme_scores, key=theme_scores.get)

    def group_by_project(
        self,
        activities: List[WorkActivity],
    ) -> Dict[str, List[WorkActivity]]:
        """
        Group activities by project/repository.

        Returns dict of project_name -> [activities]
        """
        groups = defaultdict(list)

        for activity in activities:
            project = activity.repo_or_project or "Other"
            groups[project].append(activity)

        return dict(groups)

    def group_by_theme(
        self,
        activities: List[WorkActivity],
    ) -> Dict[str, List[WorkActivity]]:
        """
        Group activities by detected theme.

        Returns dict of theme -> [activities]
        """
        groups = defaultdict(list)

        for activity in activities:
            text = f"{activity.title} {activity.description or ''}".lower()
            assigned_theme = None

            for theme, keywords in THEME_KEYWORDS.items():
                for keyword in keywords:
                    if keyword in text:
                        assigned_theme = theme
                        break
                if assigned_theme:
                    break

            if not assigned_theme:
                assigned_theme = "building"

            groups[assigned_theme].append(activity)

        return dict(groups)

    def select_top_activities(
        self,
        activities: List[WorkActivity],
        max_count: int = 5,
        min_significance: float = 0.3,
    ) -> List[WorkActivity]:
        """
        Select the most significant activities for draft generation.

        Args:
            activities: All activities
            max_count: Maximum number to select
            min_significance: Minimum significance score

        Returns:
            Top activities sorted by significance
        """
        # Filter by minimum significance
        significant = [a for a in activities if a.significance_score >= min_significance]

        # Sort by significance and take top N
        sorted_activities = sorted(
            significant,
            key=lambda a: a.significance_score,
            reverse=True,
        )

        return sorted_activities[:max_count]

    def calculate_aggregate_score(self, activities: List[WorkActivity]) -> float:
        """
        Calculate an aggregate significance score for a set of activities.

        Used to determine if there's enough activity to generate a draft.
        """
        if not activities:
            return 0.0

        # Weighted sum with diminishing returns
        sorted_scores = sorted(
            [a.significance_score for a in activities],
            reverse=True,
        )

        total = 0.0
        for i, score in enumerate(sorted_scores):
            # Each additional activity adds less weight
            weight = 1.0 / (i + 1)
            total += score * weight

        return min(total, 1.0)

    def generate_activity_summary(
        self,
        activities: List[WorkActivity],
        max_length: int = 500,
    ) -> str:
        """
        Generate a text summary of activities for the draft generator.

        This summary is included in the prompt to help the AI understand
        what work was done.
        """
        if not activities:
            return "No significant activities today."

        # Group by project
        by_project = self.group_by_project(activities)

        lines = []
        for project, project_activities in by_project.items():
            lines.append(f"\n**{project}**:")

            for activity in project_activities[:3]:  # Max 3 per project
                activity_text = f"- {activity.activity_type}: {activity.title}"

                # Add metrics if significant
                if activity.lines_added > 100:
                    activity_text += f" (+{activity.lines_added} lines)"

                lines.append(activity_text)

            if len(project_activities) > 3:
                lines.append(f"  ...and {len(project_activities) - 3} more")

        summary = "\n".join(lines)

        # Truncate if too long
        if len(summary) > max_length:
            summary = summary[:max_length - 3] + "..."

        return summary

    async def prepare_digest(
        self,
        user_id: str,
        target_date: date = None,
        min_activities: int = 1,
        min_aggregate_score: float = 0.3,
    ) -> Optional[Dict[str, Any]]:
        """
        Prepare a complete digest for draft generation.

        Args:
            user_id: User ID
            target_date: Date to aggregate
            min_activities: Minimum activities required
            min_aggregate_score: Minimum aggregate score to generate draft

        Returns:
            Digest data for draft generation, or None if insufficient activity
        """
        activities = await self.get_daily_activities(user_id, target_date)

        if len(activities) < min_activities:
            logger.info(f"User {user_id}: Only {len(activities)} activities, skipping digest")
            return None

        # Calculate aggregate score
        aggregate_score = self.calculate_aggregate_score(activities)

        if aggregate_score < min_aggregate_score:
            logger.info(f"User {user_id}: Aggregate score {aggregate_score:.2f} below threshold")
            return None

        # Prepare digest data
        top_activities = self.select_top_activities(activities)
        theme = self.detect_theme(top_activities)
        summary = self.generate_activity_summary(top_activities)

        # Get X account for this user
        x_account_result = await self.db.execute(
            select(XAccount)
            .where(
                and_(
                    XAccount.user_id == user_id,
                    XAccount.is_connected == True,
                )
            )
            .limit(1)
        )
        x_account = x_account_result.scalar_one_or_none()

        if not x_account:
            logger.warning(f"User {user_id}: No connected X account found")
            return None

        return {
            "user_id": user_id,
            "x_account_id": x_account.id,
            "date": target_date or datetime.utcnow().date(),
            "theme": theme,
            "activities": top_activities,
            "activity_ids": [a.id for a in top_activities],
            "summary": summary,
            "aggregate_score": aggregate_score,
            "total_activities": len(activities),
        }


async def get_activity_aggregator(db: AsyncSession) -> ActivityAggregator:
    """Create an activity aggregator instance."""
    return ActivityAggregator(db)
