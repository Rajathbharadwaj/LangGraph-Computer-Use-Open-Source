"""
Polling Service for Notion and Figma.

These platforms don't support webhooks, so we poll
for changes periodically using their respective APIs.

Runs every 15 minutes to check for new activities.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from database.models import WorkIntegration, WorkIntegrationCredential, WorkActivity
from ..config import (
    get_work_integrations_settings,
    ACTIVITY_SIGNIFICANCE,
    CATEGORY_MULTIPLIERS,
)
from ..clients.notion_client import NotionClient
from ..clients.figma_client import FigmaClient

logger = logging.getLogger(__name__)


class PollingService:
    """
    Service that polls Notion and Figma for activities.

    Runs on a schedule to fetch recent changes and
    create WorkActivity records.
    """

    def __init__(self):
        self.settings = get_work_integrations_settings()
        self.scheduler = AsyncIOScheduler()
        self._initialized = False

    async def initialize(self):
        """Start the polling scheduler."""
        if self._initialized:
            return

        # Poll every 15 minutes
        self.scheduler.add_job(
            self.poll_all_integrations,
            IntervalTrigger(minutes=15),
            id='work_integrations_polling',
            name='Poll Notion and Figma for activities',
            replace_existing=True,
        )

        self.scheduler.start()
        self._initialized = True
        logger.info("Work integrations polling service started (every 15 minutes)")

    async def shutdown(self):
        """Stop the polling scheduler."""
        if self._initialized:
            self.scheduler.shutdown(wait=False)
            self._initialized = False
            logger.info("Work integrations polling service stopped")

    async def poll_all_integrations(self):
        """Poll all active Notion and Figma integrations."""
        logger.info("Starting work integrations poll cycle")

        # Create database session
        from database.database import ASYNC_DATABASE_URL
        engine = create_async_engine(ASYNC_DATABASE_URL, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as db:
            try:
                # Get all active Notion and Figma integrations
                result = await db.execute(
                    select(WorkIntegration).where(
                        WorkIntegration.platform.in_(["notion", "figma"]),
                        WorkIntegration.is_active == True,
                        WorkIntegration.is_connected == True,
                    )
                )
                integrations = result.scalars().all()

                logger.info(f"Found {len(integrations)} polling integrations")

                for integration in integrations:
                    try:
                        if integration.platform == "notion":
                            await self._poll_notion(integration, db)
                        elif integration.platform == "figma":
                            await self._poll_figma(integration, db)
                    except Exception as e:
                        logger.error(
                            f"Error polling {integration.platform} integration "
                            f"{integration.id}: {e}"
                        )
                        continue

            except Exception as e:
                logger.error(f"Error in polling cycle: {e}")
            finally:
                await engine.dispose()

        logger.info("Completed work integrations poll cycle")

    async def _get_access_token(
        self,
        integration: WorkIntegration,
        db: AsyncSession,
    ) -> Optional[str]:
        """Get decrypted access token for integration."""
        from cryptography.fernet import Fernet
        import os

        result = await db.execute(
            select(WorkIntegrationCredential).where(
                WorkIntegrationCredential.integration_id == integration.id
            )
        )
        credential = result.scalar_one_or_none()

        if not credential or not credential.encrypted_access_token:
            return None

        # Decrypt token
        encryption_key = os.environ.get("WORK_INTEGRATION_ENCRYPTION_KEY")
        if not encryption_key:
            logger.error("WORK_INTEGRATION_ENCRYPTION_KEY not set")
            return None

        try:
            fernet = Fernet(encryption_key.encode())
            return fernet.decrypt(credential.encrypted_access_token.encode()).decode()
        except Exception as e:
            logger.error(f"Failed to decrypt token: {e}")
            return None

    async def _poll_notion(
        self,
        integration: WorkIntegration,
        db: AsyncSession,
    ):
        """Poll Notion for recent page updates."""
        logger.info(f"Polling Notion integration {integration.id}")

        access_token = await self._get_access_token(integration, db)
        if not access_token:
            logger.warning(f"No access token for Notion integration {integration.id}")
            return

        client = NotionClient(access_token)

        # Get pages edited in the last hour (overlap with poll interval)
        since = datetime.utcnow() - timedelta(hours=1)
        database_ids = integration.notion_database_ids or []

        try:
            pages = await client.get_recently_edited_pages(
                since=since,
                database_ids=database_ids if database_ids else None,
                limit=20,
            )

            for page in pages:
                await self._create_notion_activity(page, integration, client, db)

        except Exception as e:
            logger.error(f"Error polling Notion: {e}")
            raise

    async def _create_notion_activity(
        self,
        page: Dict[str, Any],
        integration: WorkIntegration,
        client: NotionClient,
        db: AsyncSession,
    ):
        """Create activity from Notion page update."""
        page_id = page.get("id", "").replace("-", "")
        last_edited = page.get("last_edited_time", "")

        # Check if we already have this activity
        result = await db.execute(
            select(WorkActivity).where(
                WorkActivity.integration_id == integration.id,
                WorkActivity.platform == "notion",
                WorkActivity.metadata.contains({"page_id": page_id}),
                WorkActivity.activity_at >= datetime.utcnow() - timedelta(hours=2),
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Already tracked this update
            return

        # Extract page info
        title = client.extract_page_title(page)
        url = page.get("url", "")
        parent = page.get("parent", {})

        # Determine project/database name
        project = ""
        if parent.get("type") == "database_id":
            project = parent.get("database_id", "")[:8]

        # Calculate significance
        base_score = ACTIVITY_SIGNIFICANCE.get("comment_added", 0.2)
        category = "progress"
        multiplier = CATEGORY_MULTIPLIERS.get(category, 1.0)
        significance = base_score * multiplier

        # Create activity
        activity = WorkActivity(
            integration_id=integration.id,
            user_id=integration.user_id,
            platform="notion",
            activity_type="page_updated",
            category=category,
            title=f"Updated page: {title}",
            description=f"Edited Notion page",
            url=url,
            repo_or_project=project,
            significance_score=significance,
            metadata={
                "page_id": page_id,
                "title": title,
                "parent_type": parent.get("type"),
            },
            activity_at=datetime.fromisoformat(
                last_edited.replace("Z", "+00:00")
            ).replace(tzinfo=None) if last_edited else datetime.utcnow(),
        )

        db.add(activity)
        await db.commit()
        logger.info(f"Created Notion page activity for: {title}")

    async def _poll_figma(
        self,
        integration: WorkIntegration,
        db: AsyncSession,
    ):
        """Poll Figma for recent file updates and comments."""
        logger.info(f"Polling Figma integration {integration.id}")

        access_token = await self._get_access_token(integration, db)
        if not access_token:
            logger.warning(f"No access token for Figma integration {integration.id}")
            return

        client = FigmaClient(access_token)

        # Get recently modified files
        since = datetime.utcnow() - timedelta(hours=1)
        project_ids = integration.figma_project_ids or []

        if not project_ids:
            logger.debug(f"No Figma projects configured for integration {integration.id}")
            return

        try:
            # Get recently modified files
            files = await client.get_recently_modified_files(
                project_ids=project_ids,
                since=since,
                limit=10,
            )

            for file in files:
                await self._create_figma_file_activity(file, integration, db)

            # Get recent comments
            file_keys = [f.get("key") for f in files if f.get("key")]
            if file_keys:
                comments = await client.get_recent_comments(
                    file_keys=file_keys,
                    since=since,
                    limit=20,
                )

                for comment in comments:
                    await self._create_figma_comment_activity(comment, integration, db)

            # Get recent versions (saves)
            if file_keys:
                versions = await client.get_recent_versions(
                    file_keys=file_keys,
                    since=since,
                    limit=10,
                )

                for version in versions:
                    await self._create_figma_version_activity(version, integration, db)

        except Exception as e:
            logger.error(f"Error polling Figma: {e}")
            raise

    async def _create_figma_file_activity(
        self,
        file: Dict[str, Any],
        integration: WorkIntegration,
        db: AsyncSession,
    ):
        """Create activity from Figma file update."""
        file_key = file.get("key", "")
        name = file.get("name", "")
        last_modified = file.get("lastModified", "")

        # Check if we already have this activity
        result = await db.execute(
            select(WorkActivity).where(
                WorkActivity.integration_id == integration.id,
                WorkActivity.platform == "figma",
                WorkActivity.activity_type == "file_updated",
                WorkActivity.metadata.contains({"file_key": file_key}),
                WorkActivity.activity_at >= datetime.utcnow() - timedelta(hours=2),
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            return

        # Calculate significance
        base_score = ACTIVITY_SIGNIFICANCE.get("comment_added", 0.2)
        category = "progress"
        multiplier = CATEGORY_MULTIPLIERS.get(category, 1.0)
        significance = base_score * multiplier

        # Create activity
        activity = WorkActivity(
            integration_id=integration.id,
            user_id=integration.user_id,
            platform="figma",
            activity_type="file_updated",
            category=category,
            title=f"Updated design: {name}",
            description=f"Made changes to Figma file",
            url=f"https://www.figma.com/file/{file_key}",
            repo_or_project=file.get("project_id", ""),
            significance_score=significance,
            metadata={
                "file_key": file_key,
                "name": name,
                "thumbnail_url": file.get("thumbnailUrl"),
            },
            activity_at=datetime.fromisoformat(
                last_modified.replace("Z", "+00:00")
            ).replace(tzinfo=None) if last_modified else datetime.utcnow(),
        )

        db.add(activity)
        await db.commit()
        logger.info(f"Created Figma file activity for: {name}")

    async def _create_figma_comment_activity(
        self,
        comment: Dict[str, Any],
        integration: WorkIntegration,
        db: AsyncSession,
    ):
        """Create activity from Figma comment."""
        comment_id = comment.get("id", "")
        message = comment.get("message", "")
        file_key = comment.get("file_key", "")
        created_at = comment.get("created_at", "")

        # Check if we already have this
        result = await db.execute(
            select(WorkActivity).where(
                WorkActivity.integration_id == integration.id,
                WorkActivity.platform == "figma",
                WorkActivity.metadata.contains({"comment_id": comment_id}),
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            return

        # Calculate significance
        base_score = ACTIVITY_SIGNIFICANCE.get("comment_added", 0.2)
        category = "collaboration"
        multiplier = CATEGORY_MULTIPLIERS.get(category, 1.0)
        significance = base_score * multiplier

        # Create activity
        activity = WorkActivity(
            integration_id=integration.id,
            user_id=integration.user_id,
            platform="figma",
            activity_type="comment_added",
            category=category,
            title="Added design feedback",
            description=message[:500] if len(message) > 500 else message,
            url=f"https://www.figma.com/file/{file_key}",
            repo_or_project=file_key,
            significance_score=significance,
            metadata={
                "comment_id": comment_id,
                "file_key": file_key,
            },
            activity_at=datetime.fromisoformat(
                created_at.replace("Z", "+00:00")
            ).replace(tzinfo=None) if created_at else datetime.utcnow(),
        )

        db.add(activity)
        await db.commit()
        logger.info(f"Created Figma comment activity")

    async def _create_figma_version_activity(
        self,
        version: Dict[str, Any],
        integration: WorkIntegration,
        db: AsyncSession,
    ):
        """Create activity from Figma version save."""
        version_id = version.get("id", "")
        label = version.get("label", "")
        description = version.get("description", "")
        file_key = version.get("file_key", "")
        created_at = version.get("created_at", "")

        # Only track labeled versions (intentional saves)
        if not label:
            return

        # Check if we already have this
        result = await db.execute(
            select(WorkActivity).where(
                WorkActivity.integration_id == integration.id,
                WorkActivity.platform == "figma",
                WorkActivity.metadata.contains({"version_id": version_id}),
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            return

        # Calculate significance - version saves are more significant
        base_score = ACTIVITY_SIGNIFICANCE.get("commits_pushed", 0.3)
        category = "progress"
        multiplier = CATEGORY_MULTIPLIERS.get(category, 1.0)
        significance = base_score * multiplier

        # Create activity
        activity = WorkActivity(
            integration_id=integration.id,
            user_id=integration.user_id,
            platform="figma",
            activity_type="version_saved",
            category=category,
            title=f"Saved version: {label}",
            description=description or f"Created design checkpoint: {label}",
            url=f"https://www.figma.com/file/{file_key}",
            repo_or_project=file_key,
            significance_score=significance,
            metadata={
                "version_id": version_id,
                "label": label,
                "file_key": file_key,
            },
            activity_at=datetime.fromisoformat(
                created_at.replace("Z", "+00:00")
            ).replace(tzinfo=None) if created_at else datetime.utcnow(),
        )

        db.add(activity)
        await db.commit()
        logger.info(f"Created Figma version activity: {label}")


# Singleton instance
_service: Optional[PollingService] = None


def get_polling_service() -> PollingService:
    """Get or create the polling service."""
    global _service
    if _service is None:
        _service = PollingService()
    return _service


async def start_polling_service():
    """Initialize and start the polling service."""
    service = get_polling_service()
    await service.initialize()
    return service
