"""
Draft Generator Service for Work Integrations.

Generates AI-powered draft X posts from work activities
using the user's writing style.
"""

import logging
import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from anthropic import Anthropic

from database.models import ActivityDraft, WorkActivity
from ..config import get_work_integrations_settings

logger = logging.getLogger(__name__)

# Initialize Anthropic client
anthropic = Anthropic()


class GeneratedDraft(BaseModel):
    """A generated draft post."""
    content: str = Field(description="The post content (max 280 chars for single post)")
    rationale: str = Field(description="Why this angle was chosen")
    theme: str = Field(description="The detected theme of the post")


# Prompt templates for different themes
THEME_PROMPTS = {
    "shipping": """Focus on the excitement of shipping and getting things to users.
Use language that conveys momentum and progress.
Celebrate the milestone without being boastful.""",

    "building": """Focus on the technical journey and what was built.
Share insights about the process or architecture decisions.
Make it educational for other builders.""",

    "fixing": """Frame bug fixes as improving user experience.
Don't dwell on what was broken - focus on the solution.
Share any learnings that others might find useful.""",

    "improving": """Highlight the before/after improvements.
Explain why the refactoring or optimization was valuable.
Share metrics if available (performance, code quality).""",

    "collaborating": """Acknowledge collaboration and teamwork.
Highlight good discussions or helpful feedback.
Show appreciation for the community/team.""",

    "learning": """Share the learning journey authentically.
Be humble about what you didn't know before.
Pass on insights to help others learn faster.""",

    "documenting": """Emphasize the value of good documentation.
Preview what readers will learn from the docs.
Encourage others to contribute or give feedback.""",
}


class DraftGenerator:
    """
    Generates X post drafts from work activities.

    Uses Claude to generate posts that:
    - Match the user's writing style
    - Highlight significant work activities
    - Are engaging and authentic
    - Fit within X's character limits
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_work_integrations_settings()

    async def get_user_style_prompt(self, user_id: str) -> str:
        """
        Get the user's writing style prompt.

        Imports from user_writing_style module.
        """
        try:
            from user_writing_style import get_user_style_prompt
            return get_user_style_prompt(user_id)
        except Exception as e:
            logger.warning(f"Could not load user style for {user_id}: {e}")
            return "Write in a professional but friendly tone."

    async def get_user_preferences_prompt(self, user_id: str) -> str:
        """
        Get user preferences from the preferences table.

        Includes guardrails from the onboarding wizard.
        """
        try:
            from sqlalchemy import select
            from database.models import User

            # This would query the user_preferences table
            # For now, return empty - will be enhanced later
            return ""
        except Exception:
            return ""

    def build_generation_prompt(
        self,
        digest: Dict[str, Any],
        style_prompt: str,
        preferences_prompt: str = "",
    ) -> str:
        """
        Build the full prompt for draft generation.

        Combines:
        - Activity summary
        - Theme-specific guidance
        - User's writing style
        - User preferences/guardrails
        """
        theme = digest.get("theme", "building")
        theme_guidance = THEME_PROMPTS.get(theme, THEME_PROMPTS["building"])

        activities_text = digest.get("summary", "")

        prompt = f"""You are generating an X (Twitter) post about work activities for a "build in public" style update.

## Today's Activities
{activities_text}

## Theme: {theme.title()}
{theme_guidance}

## Writing Style Guidelines
{style_prompt}

{f"## User Preferences" + chr(10) + preferences_prompt if preferences_prompt else ""}

## Instructions
1. Write a single X post (max 280 characters) that shares this work activity authentically
2. Match the user's writing style exactly
3. Focus on what was accomplished, not just what was done
4. Be genuine - avoid corporate speak or excessive emojis
5. Include 0-2 relevant hashtags only if they feel natural
6. Don't start with "I just..." or similar overused patterns
7. Make it interesting to fellow builders/developers

## Output Format
Respond with ONLY the post content. No quotes, no explanation, just the post text."""

        return prompt

    async def generate_draft(
        self,
        digest: Dict[str, Any],
        num_variations: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Generate draft posts from a digest.

        Args:
            digest: Prepared digest from ActivityAggregator
            num_variations: Number of draft variations to generate

        Returns:
            List of generated drafts with content and metadata
        """
        user_id = digest["user_id"]

        # Get user's style
        style_prompt = await self.get_user_style_prompt(user_id)
        preferences_prompt = await self.get_user_preferences_prompt(user_id)

        # Build prompt
        prompt = self.build_generation_prompt(digest, style_prompt, preferences_prompt)

        drafts = []

        for i in range(num_variations):
            try:
                # Generate with Claude
                response = anthropic.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=300,
                    temperature=0.7 + (i * 0.1),  # Vary temperature for diversity
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                )

                content = response.content[0].text.strip()

                # Clean up content
                content = self._clean_content(content)

                # Validate length
                if len(content) > 280:
                    logger.warning(f"Draft exceeded 280 chars ({len(content)}), truncating")
                    content = content[:277] + "..."

                drafts.append({
                    "content": content,
                    "theme": digest["theme"],
                    "activity_ids": digest["activity_ids"],
                    "summary": digest["summary"],
                    "variation": i + 1,
                })

            except Exception as e:
                logger.error(f"Error generating draft variation {i + 1}: {e}")
                continue

        return drafts

    def _clean_content(self, content: str) -> str:
        """Clean up generated content."""
        # Remove quotes if wrapped
        if content.startswith('"') and content.endswith('"'):
            content = content[1:-1]

        # Remove common AI patterns
        content = content.replace("🚀 ", "").replace("✨ ", "")

        # Trim whitespace
        content = content.strip()

        return content

    async def create_draft_record(
        self,
        user_id: str,
        x_account_id: int,
        draft_data: Dict[str, Any],
        digest_date: datetime.date,
    ) -> ActivityDraft:
        """
        Create an ActivityDraft record in the database.

        Args:
            user_id: User ID
            x_account_id: X account ID
            draft_data: Generated draft data
            digest_date: Date of the digest

        Returns:
            Created ActivityDraft record
        """
        draft = ActivityDraft(
            user_id=user_id,
            x_account_id=x_account_id,
            content=draft_data["content"],
            ai_rationale=f"Theme: {draft_data['theme']}. Variation {draft_data.get('variation', 1)} of the daily digest.",
            source_activity_ids=draft_data["activity_ids"],
            activity_summary=draft_data["summary"],
            digest_date=digest_date,
            digest_theme=draft_data["theme"],
            status="pending",
            expires_at=datetime.utcnow() + timedelta(days=self.settings.draft_expiration_days),
        )

        self.db.add(draft)
        await self.db.flush()

        # Mark source activities as processed
        for activity_id in draft_data["activity_ids"]:
            result = await self.db.execute(
                select(WorkActivity).where(WorkActivity.id == activity_id)
            )
            activity = result.scalar_one_or_none()
            if activity:
                activity.processed = True
                activity.processed_at = datetime.utcnow()
                activity.draft_id = draft.id

        logger.info(f"Created draft {draft.id} for user {user_id}: {draft_data['content'][:50]}...")

        return draft

    async def generate_and_save_drafts(
        self,
        digest: Dict[str, Any],
        num_drafts: int = 1,
    ) -> List[ActivityDraft]:
        """
        Generate drafts and save to database.

        Args:
            digest: Prepared digest from ActivityAggregator
            num_drafts: Number of drafts to generate (1-2 recommended)

        Returns:
            List of created ActivityDraft records
        """
        # Generate draft content
        draft_contents = await self.generate_draft(digest, num_drafts)

        if not draft_contents:
            logger.warning(f"No drafts generated for user {digest['user_id']}")
            return []

        # Save to database
        saved_drafts = []
        for draft_data in draft_contents:
            draft = await self.create_draft_record(
                user_id=digest["user_id"],
                x_account_id=digest["x_account_id"],
                draft_data=draft_data,
                digest_date=digest["date"],
            )
            saved_drafts.append(draft)

        return saved_drafts


async def get_draft_generator(db: AsyncSession) -> DraftGenerator:
    """Create a draft generator instance."""
    return DraftGenerator(db)
