"""
Daily Digest Executor for Work Integrations.

Runs daily at a configurable time (default 9 PM) to:
1. Find all users with active work integrations
2. Aggregate their daily activities
3. Generate draft posts
4. Notify users of pending drafts
"""

import logging
import asyncio
from datetime import datetime, date
from typing import List, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from database.models import WorkIntegration, User
from .activity_aggregator import ActivityAggregator
from .draft_generator import DraftGenerator
from ..config import get_work_integrations_settings

logger = logging.getLogger(__name__)


class DailyDigestExecutor:
    """
    Executes daily digest generation for all users with work integrations.

    Scheduled to run at 9 PM (configurable) each day.
    """

    def __init__(self, database_url: str = None):
        self.settings = get_work_integrations_settings()
        self.scheduler = AsyncIOScheduler(timezone='UTC')
        self.is_running = False

        # Database setup
        import os
        self.database_url = database_url or os.getenv(
            "POSTGRES_URI",
            os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:password@localhost:5432/xgrowth")
        )

        # Ensure async driver
        if "postgresql://" in self.database_url and "+asyncpg" not in self.database_url:
            self.database_url = self.database_url.replace("postgresql://", "postgresql+asyncpg://")

        self.engine = None
        self.async_session = None

    async def initialize(self):
        """Initialize the executor and schedule the daily job."""
        try:
            # Create async engine
            self.engine = create_async_engine(self.database_url, echo=False)
            self.async_session = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

            # Schedule daily digest job
            self.scheduler.add_job(
                self.run_daily_digest,
                CronTrigger(
                    hour=self.settings.daily_digest_hour,
                    minute=0,
                    timezone='UTC'
                ),
                id='daily_work_digest',
                name='Daily Work Activity Digest',
                replace_existing=True,
            )

            self.scheduler.start()
            self.is_running = True

            logger.info(
                f"✅ DailyDigestExecutor initialized. "
                f"Scheduled for {self.settings.daily_digest_hour}:00 UTC daily."
            )

        except Exception as e:
            logger.error(f"❌ Failed to initialize DailyDigestExecutor: {e}")
            raise

    async def shutdown(self):
        """Shutdown the executor."""
        if self.is_running:
            self.scheduler.shutdown(wait=False)
            self.is_running = False

            if self.engine:
                await self.engine.dispose()

            logger.info("DailyDigestExecutor shutdown complete")

    async def get_users_with_integrations(
        self,
        db: AsyncSession,
    ) -> List[str]:
        """Get all user IDs with active work integrations."""
        result = await db.execute(
            select(WorkIntegration.user_id)
            .where(
                and_(
                    WorkIntegration.is_connected == True,
                    WorkIntegration.is_active == True,
                )
            )
            .distinct()
        )
        return [row[0] for row in result.fetchall()]

    async def process_user_digest(
        self,
        db: AsyncSession,
        user_id: str,
        target_date: date = None,
    ) -> int:
        """
        Process digest for a single user.

        Args:
            db: Database session
            user_id: User ID
            target_date: Date to process (defaults to today)

        Returns:
            Number of drafts created
        """
        try:
            # Create aggregator and generator
            aggregator = ActivityAggregator(db)
            generator = DraftGenerator(db)

            # Prepare digest
            digest = await aggregator.prepare_digest(user_id, target_date)

            if not digest:
                logger.debug(f"User {user_id}: No digest to generate")
                return 0

            # Generate and save drafts (1-2 drafts per day)
            num_drafts = 1 if digest["aggregate_score"] < 0.7 else 2
            drafts = await generator.generate_and_save_drafts(digest, num_drafts)

            await db.commit()

            logger.info(
                f"User {user_id}: Generated {len(drafts)} drafts from "
                f"{digest['total_activities']} activities (theme: {digest['theme']})"
            )

            return len(drafts)

        except Exception as e:
            logger.error(f"Error processing digest for user {user_id}: {e}")
            await db.rollback()
            return 0

    async def run_daily_digest(self, target_date: date = None):
        """
        Run the daily digest for all users.

        This is called by the scheduler at the configured time.
        """
        start_time = datetime.utcnow()
        logger.info(f"🚀 Starting daily digest run at {start_time}")

        if target_date is None:
            target_date = datetime.utcnow().date()

        total_users = 0
        total_drafts = 0
        errors = 0

        async with self.async_session() as db:
            # Get all users with active integrations
            user_ids = await self.get_users_with_integrations(db)
            total_users = len(user_ids)

            logger.info(f"Processing digest for {total_users} users")

            # Process each user
            for user_id in user_ids:
                try:
                    drafts_created = await self.process_user_digest(db, user_id, target_date)
                    total_drafts += drafts_created
                except Exception as e:
                    logger.error(f"Failed to process user {user_id}: {e}")
                    errors += 1

        # Log summary
        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.info(
            f"✅ Daily digest complete: "
            f"{total_users} users, {total_drafts} drafts created, "
            f"{errors} errors, {duration:.2f}s"
        )

        return {
            "users_processed": total_users,
            "drafts_created": total_drafts,
            "errors": errors,
            "duration_seconds": duration,
        }

    async def run_for_user(self, user_id: str, target_date: date = None) -> int:
        """
        Run digest for a specific user (for testing or manual trigger).

        Args:
            user_id: User ID
            target_date: Date to process

        Returns:
            Number of drafts created
        """
        async with self.async_session() as db:
            return await self.process_user_digest(db, user_id, target_date)


# Singleton instance
_digest_executor: Optional[DailyDigestExecutor] = None


async def get_daily_digest_executor() -> DailyDigestExecutor:
    """Get or create the daily digest executor singleton."""
    global _digest_executor
    if _digest_executor is None:
        _digest_executor = DailyDigestExecutor()
        await _digest_executor.initialize()
    return _digest_executor


async def shutdown_daily_digest_executor():
    """Shutdown the daily digest executor."""
    global _digest_executor
    if _digest_executor:
        await _digest_executor.shutdown()
        _digest_executor = None
