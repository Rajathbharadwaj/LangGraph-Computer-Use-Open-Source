"""
Scheduled Post Executor
Manages automated posting of scheduled content through the Deep Agent.
Uses APScheduler to trigger LangGraph agent runs at specific scheduled times.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import asyncio
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

# LangGraph SDK client
from langgraph_sdk import get_client

logger = logging.getLogger(__name__)

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5433/xgrowth")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# LangGraph server URL
LANGGRAPH_URL = os.getenv("LANGGRAPH_URL", "http://localhost:8124")


class ScheduledPostExecutor:
    """Manages scheduled post execution through LangGraph Deep Agent"""

    def __init__(self, langgraph_url: str = LANGGRAPH_URL):
        self.scheduler = AsyncIOScheduler()
        self.scheduled_jobs = {}
        self.is_running = False
        self.langgraph_url = langgraph_url
        self.client = None

    async def initialize(self):
        """Initialize scheduler, LangGraph client, and load pending posts"""
        # Initialize LangGraph SDK client
        self.client = get_client(url=self.langgraph_url)

        # Start scheduler
        self.scheduler.start()
        self.is_running = True
        logger.info("✅ Scheduled post executor initialized")
        logger.info(f"📡 Connected to LangGraph server: {self.langgraph_url}")

        # Load and schedule all pending posts from database
        await self.load_pending_posts()

    async def load_pending_posts(self):
        """Load all scheduled posts from database and schedule them"""
        from database.models import ScheduledPost, XAccount

        db = SessionLocal()
        try:
            # Get all scheduled posts that haven't been posted yet
            now = datetime.now()
            pending_posts = db.query(ScheduledPost).filter(
                ScheduledPost.status == "scheduled",
                ScheduledPost.scheduled_at > now
            ).all()

            logger.info(f"📋 Loading {len(pending_posts)} pending scheduled posts...")

            for post in pending_posts:
                # Get the X account info
                x_account = db.query(XAccount).filter(
                    XAccount.id == post.x_account_id
                ).first()

                if not x_account:
                    logger.warning(f"⚠️ No X account found for post {post.id}")
                    continue

                # Schedule the post
                self.schedule_post(
                    post_id=post.id,
                    post_content=post.content,
                    scheduled_time=post.scheduled_at,
                    user_id=x_account.user_id,
                    username=x_account.username,
                    media_urls=post.media_urls or []
                )

            logger.info(f"✅ Scheduled {len(pending_posts)} posts")

        except Exception as e:
            logger.error(f"❌ Failed to load pending posts: {e}")
        finally:
            db.close()

    def schedule_post(
        self,
        post_id: int,
        post_content: str,
        scheduled_time: datetime,
        user_id: str,
        username: str,
        media_urls: List[str] = None
    ) -> str:
        """
        Schedule a post for execution at a specific time

        Args:
            post_id: Database ID of the scheduled post
            post_content: The content to post to X/Twitter
            scheduled_time: When the post should be published
            user_id: User ID from Clerk
            username: X/Twitter username
            media_urls: Optional list of media URLs

        Returns:
            Job ID of the scheduled task
        """
        job_id = f"post_{post_id}"

        # Check if post is in the past
        if scheduled_time <= datetime.now():
            logger.warning(f"⚠️ Post {post_id} scheduled for past time {scheduled_time}, skipping (should be handled by caller)")
            return job_id

        # Add the scheduled job - create a wrapper to pass all args
        async def execute_wrapper():
            await self._execute_post_action(post_id, post_content, user_id, username, media_urls)

        job = self.scheduler.add_job(
            func=execute_wrapper,
            trigger=DateTrigger(run_date=scheduled_time),
            id=job_id,
            replace_existing=True
        )

        self.scheduled_jobs[job_id] = {
            "post_id": post_id,
            "scheduled_time": scheduled_time,
            "content": post_content[:100],
            "user_id": user_id,
            "username": username,
            "job": job
        }

        logger.info(f"📅 Post {post_id} scheduled for {scheduled_time} (@{username})")
        return job_id

    async def _execute_post_action(
        self,
        post_id: int,
        post_content: str,
        user_id: str,
        username: str,
        media_urls: Optional[List[str]] = None
    ):
        """Execute the post through the Deep Agent via LangGraph SDK"""
        from database.models import ScheduledPost

        db = SessionLocal()
        job_id = f"post_{post_id}"

        try:
            logger.info(f"🚀 Executing scheduled post {post_id} for @{username}")
            logger.info(f"📝 Content: {post_content[:100]}...")

            # Create a thread for this post execution
            thread = await self.client.threads.create()
            thread_id = thread["thread_id"]

            logger.info(f"📌 Created thread: {thread_id}")

            # Prepare input for the deep agent
            agent_input = {
                "messages": [
                    {
                        "role": "user",
                        "content": f"Post this to X: {post_content}"
                    }
                ],
                "user_id": user_id,
                "user_handle": username,
                "action": "create_post_on_x",
                "post_content": post_content,
                "media_urls": media_urls or [],
                "scheduled_post_id": post_id
            }

            # Execute through deep agent using LangGraph SDK
            # Using the deployed x_growth_deep_agent
            assistant_id = "x_growth_deep_agent"

            logger.info(f"🤖 Invoking deep agent...")
            result = await self.client.runs.wait(
                thread_id=thread_id,
                assistant_id=assistant_id,
                input=agent_input
            )

            logger.info(f"✅ Agent execution completed: {result}")

            # Update database - mark as posted
            post = db.query(ScheduledPost).filter(ScheduledPost.id == post_id).first()
            if post:
                post.status = "posted"
                post.posted_at = datetime.now()
                db.commit()
                logger.info(f"✅ Post {post_id} marked as posted in database")

            # Update job status
            if job_id in self.scheduled_jobs:
                self.scheduled_jobs[job_id]["status"] = "completed"
                self.scheduled_jobs[job_id]["result"] = result

            return result

        except Exception as e:
            logger.error(f"❌ Failed to execute post {post_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())

            # Update database - mark as failed
            try:
                post = db.query(ScheduledPost).filter(ScheduledPost.id == post_id).first()
                if post:
                    post.status = "failed"
                    db.commit()
            except Exception as db_error:
                logger.error(f"❌ Failed to update post status in DB: {db_error}")

            # Update job status
            if job_id in self.scheduled_jobs:
                self.scheduled_jobs[job_id]["status"] = "failed"
                self.scheduled_jobs[job_id]["error"] = str(e)

            raise

        finally:
            db.close()

    def cancel_scheduled_post(self, post_id: int) -> bool:
        """Cancel a scheduled post"""
        job_id = f"post_{post_id}"

        if job_id in self.scheduled_jobs:
            try:
                job = self.scheduled_jobs[job_id]["job"]
                job.remove()
                del self.scheduled_jobs[job_id]
                logger.info(f"🗑️ Post {post_id} cancelled")
                return True
            except Exception as e:
                logger.error(f"❌ Failed to cancel post {post_id}: {e}")
                return False

        logger.warning(f"⚠️ Post {post_id} not found in scheduled jobs")
        return False

    def reschedule_post(
        self,
        post_id: int,
        new_scheduled_time: datetime,
        post_content: str,
        user_id: str,
        username: str,
        media_urls: List[str] = None
    ) -> bool:
        """Reschedule an existing post"""
        # Cancel existing job
        self.cancel_scheduled_post(post_id)

        # Schedule with new time
        self.schedule_post(
            post_id=post_id,
            post_content=post_content,
            scheduled_time=new_scheduled_time,
            user_id=user_id,
            username=username,
            media_urls=media_urls
        )

        logger.info(f"🔄 Post {post_id} rescheduled to {new_scheduled_time}")
        return True

    def get_scheduled_posts(self) -> Dict[str, Any]:
        """Get all currently scheduled posts"""
        return {
            job_id: {
                "post_id": job_info["post_id"],
                "scheduled_time": job_info["scheduled_time"].isoformat(),
                "content_preview": job_info["content"],
                "status": job_info.get("status", "pending"),
                "username": job_info["username"]
            }
            for job_id, job_info in self.scheduled_jobs.items()
        }

    async def shutdown(self):
        """Gracefully shutdown the scheduler"""
        logger.info("🛑 Shutting down scheduled post executor...")
        self.scheduler.shutdown(wait=True)
        self.is_running = False
        logger.info("✅ Scheduled post executor shut down")


# Global executor instance
executor_instance: Optional[ScheduledPostExecutor] = None


async def get_executor() -> ScheduledPostExecutor:
    """Get or create the global executor instance"""
    global executor_instance

    if executor_instance is None:
        executor_instance = ScheduledPostExecutor()
        await executor_instance.initialize()

    return executor_instance


async def main():
    """Standalone execution for testing"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    executor = await get_executor()

    logger.info("📊 Scheduled posts:")
    for job_id, info in executor.get_scheduled_posts().items():
        logger.info(f"  - {job_id}: {info['scheduled_time']} - {info['content_preview']}")

    # Keep running
    try:
        logger.info("⏳ Executor running... Press Ctrl+C to stop")
        while executor.is_running:
            await asyncio.sleep(10)
    except KeyboardInterrupt:
        logger.info("⚠️ Received shutdown signal")
        await executor.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
