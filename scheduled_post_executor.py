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
import json
import aiohttp
import redis.asyncio as aioredis

# LangGraph SDK client
from langgraph_sdk import get_client

# VNC Session Manager for per-user browser sessions
from vnc_session_manager import VNCSessionManager, get_vnc_manager

# Billing service for credit tracking
from services.billing_service import BillingService
from services.stripe_service import AGENT_SESSION_COSTS, CREDIT_COSTS

logger = logging.getLogger(__name__)

# Extension backend URL for cookie fetching
EXTENSION_BACKEND_URL = os.environ.get("EXTENSION_BACKEND_URL", "http://127.0.0.1:8001")

# Database setup
# Check both POSTGRES_URI (LangGraph) and DATABASE_URL (backend-api)
DATABASE_URL = os.getenv("POSTGRES_URI") or os.getenv("DATABASE_URL") or "postgresql://postgres:password@localhost:5433/xgrowth"
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

        # Initialize VNC session manager
        self.vnc_manager = await get_vnc_manager()

        # Start scheduler
        self.scheduler.start()
        self.is_running = True
        logger.info("✅ Scheduled post executor initialized")
        logger.info(f"📡 Connected to LangGraph server: {self.langgraph_url}")

        # Load and schedule all pending posts from database
        await self.load_pending_posts()

    async def _get_user_vnc_url(self, user_id: str) -> Optional[str]:
        """
        Get the VNC URL for a user's browser session.

        Looks up from Redis first, then Cloud Run if not cached.
        Will auto-create a session if none exists.
        """
        try:
            # Get or create VNC session for the user
            session = await self.vnc_manager.get_or_create_session(user_id)

            if session:
                vnc_url = session.get("https_url") or session.get("service_url")
                if vnc_url:
                    logger.info(f"✅ Got VNC URL for user {user_id}: {vnc_url}")
                    return vnc_url

            logger.error(f"❌ Could not get VNC session for user {user_id}")
            return None

        except Exception as e:
            logger.error(f"❌ Failed to get VNC URL for user {user_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    async def _inject_cookies_to_vnc(self, user_id: str, vnc_url: str) -> bool:
        """
        Inject user's X/Twitter cookies into their VNC browser session.

        This ensures the agent can post as the authenticated user.
        """
        try:
            logger.info(f"🔐 Injecting cookies for user {user_id} to VNC: {vnc_url}")

            # Fetch cookies from extension backend
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'{EXTENSION_BACKEND_URL}/cookies/{user_id}',
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"❌ Extension backend returned {resp.status}")
                        return False

                    ext_data = await resp.json()
                    if not ext_data.get('success'):
                        logger.error(f"❌ No cookies found for user {user_id}")
                        return False

                    cookies = ext_data.get("cookies", [])
                    username = ext_data.get("username", "unknown")
                    logger.info(f"📦 Got {len(cookies)} cookies for @{username}")

            if not cookies:
                logger.error(f"❌ No cookies to inject for user {user_id}")
                return False

            # Convert Chrome cookies to Playwright format
            playwright_cookies = []
            for cookie in cookies:
                # Handle expiration
                expires_value = cookie.get("expirationDate", -1)
                if expires_value and expires_value != -1:
                    expires_value = int(expires_value)
                else:
                    expires_value = -1

                # Handle sameSite
                same_site = cookie.get("sameSite", "lax")
                if same_site:
                    same_site_lower = same_site.lower()
                    if same_site_lower == "strict":
                        same_site = "Strict"
                    elif same_site_lower == "lax":
                        same_site = "Lax"
                    elif same_site_lower in ("none", "no_restriction"):
                        same_site = "None"
                    else:
                        same_site = "Lax"
                else:
                    same_site = "Lax"

                pw_cookie = {
                    "name": cookie["name"],
                    "value": cookie["value"],
                    "domain": cookie.get("domain", ".x.com"),
                    "path": cookie.get("path", "/"),
                    "expires": expires_value,
                    "httpOnly": cookie.get("httpOnly", False),
                    "secure": cookie.get("secure", True),
                    "sameSite": same_site
                }
                playwright_cookies.append(pw_cookie)

            # Inject cookies to VNC (use /session/load endpoint)
            inject_url = f"{vnc_url.rstrip('/')}/session/load"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    inject_url,
                    json={"cookies": playwright_cookies},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        logger.info(f"✅ Cookies injected successfully: {result}")
                        return True
                    else:
                        error_text = await resp.text()
                        logger.error(f"❌ Cookie injection failed ({resp.status}): {error_text}")
                        return False

        except Exception as e:
            logger.error(f"❌ Cookie injection error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

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

            # Check if user has enough credits
            billing = BillingService(db)
            min_credits = AGENT_SESSION_COSTS.get("content_engine", 5)
            has_credits, reason = billing.check_credits(user_id, min_credits)
            if not has_credits:
                logger.warning(f"⚠️ Skipping scheduled post {post_id} - user {user_id} has insufficient credits: {reason}")
                # Mark as failed due to credits
                post = db.query(ScheduledPost).filter(ScheduledPost.id == post_id).first()
                if post:
                    post.status = "failed"
                    post.error_message = "Insufficient credits"
                    db.commit()
                return

            session_start_time = datetime.now()

            # Step 1: Get or create VNC session for the user
            logger.info(f"🖥️ Getting VNC session for user {user_id}...")
            vnc_url = await self._get_user_vnc_url(user_id)

            if not vnc_url:
                raise Exception(f"Could not get VNC session for user {user_id}")

            logger.info(f"✅ VNC URL: {vnc_url}")

            # Step 2: Inject cookies to ensure authenticated session
            logger.info(f"🔐 Injecting cookies for user {user_id}...")
            cookie_result = await self._inject_cookies_to_vnc(user_id, vnc_url)

            if not cookie_result:
                logger.warning(f"⚠️ Cookie injection failed, but attempting to continue...")
                # Continue anyway - cookies might already be in the session

            # Extract host and port for screenshot middleware
            cua_host = None
            cua_port = None
            if vnc_url and "://" in vnc_url:
                try:
                    url_parts = vnc_url.split("://")[1]
                    if ":" in url_parts:
                        cua_host = url_parts.split(":")[0]
                        cua_port = url_parts.split(":")[-1].rstrip("/")
                    else:
                        cua_host = url_parts.rstrip("/")
                        cua_port = "443"  # HTTPS default
                except Exception as e:
                    logger.warning(f"⚠️ Could not parse VNC URL: {e}")

            logger.info(f"🌐 CUA Host: {cua_host}, Port: {cua_port}")

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

            # Config with VNC URL for the agent to use browser automation
            config = {
                "configurable": {
                    "user_id": user_id,
                    "cua_url": vnc_url,
                    "x-cua-host": cua_host,
                    "x-cua-port": cua_port,
                    "x-user-id": user_id,
                    "use_longterm_memory": True,
                }
            }

            # Execute through deep agent using LangGraph SDK
            # Using the deployed x_growth_deep_agent
            assistant_id = "x_growth_deep_agent"

            logger.info(f"🤖 Invoking deep agent with VNC URL: {vnc_url}")
            result = await self.client.runs.wait(
                thread_id=thread_id,
                assistant_id=assistant_id,
                input=agent_input,
                config=config  # Now passing the config with cua_url!
            )

            logger.info(f"✅ Agent execution completed: {result}")

            # Update database - mark as posted
            post = db.query(ScheduledPost).filter(ScheduledPost.id == post_id).first()
            if post:
                post.status = "posted"
                post.posted_at = datetime.now()
                db.commit()
                logger.info(f"✅ Post {post_id} marked as posted in database")

            # Usage-based billing: charge credits based on actual LangSmith costs
            try:
                # Try to get run_id from result metadata
                run_id = None
                if isinstance(result, dict):
                    run_id = result.get("run_id") or result.get("metadata", {}).get("run_id")

                if run_id:
                    # Preferred: Use LangSmith to get actual cost
                    logger.info(f"💳 Getting actual cost from LangSmith for run {run_id}...")
                    billing_result = billing.consume_credits_from_langsmith(
                        user_id=user_id,
                        run_id=run_id,
                        agent_type="content_engine",
                        description=f"Scheduled post: {post_content[:30]}"
                    )
                    logger.info(f"💳 Charged {billing_result['credits_charged']} credits "
                                f"(${billing_result['actual_cost']:.2f} actual) for post {post_id}")
                else:
                    # Fallback: Use fixed estimate if no run_id
                    logger.warning(f"⚠️ No run_id available for post {post_id}, using fallback billing")
                    session_duration_minutes = (datetime.now() - session_start_time).total_seconds() / 60
                    base_cost = AGENT_SESSION_COSTS.get("content_engine", 5)
                    computer_use_cost = int(session_duration_minutes * CREDIT_COSTS.get("computer_use_minute", 5)) if vnc_url else 0
                    total_credits = base_cost + computer_use_cost

                    billing.consume_credits(
                        user_id=user_id,
                        credits=total_credits,
                        description=f"Scheduled post: {post_content[:30]}",
                        agent_type="content_engine"
                    )
                    logger.info(f"💳 Fallback billing: {total_credits} credits for post {post_id}")

            except Exception as credit_error:
                logger.warning(f"⚠️ Failed to consume credits for post {post_id}: {credit_error}")

            # Update job status
            if job_id in self.scheduled_jobs:
                self.scheduled_jobs[job_id]["status"] = "completed"
                self.scheduled_jobs[job_id]["result"] = result

            return result

        except Exception as e:
            error_message = str(e)
            logger.error(f"❌ Failed to execute post {post_id}: {error_message}")
            import traceback
            logger.error(traceback.format_exc())

            # Update database - mark as failed with error message
            try:
                post = db.query(ScheduledPost).filter(ScheduledPost.id == post_id).first()
                if post:
                    post.status = "failed"
                    post.error_message = error_message[:500]  # Truncate if too long
                    db.commit()
                    logger.info(f"📝 Post {post_id} marked as failed with error: {error_message[:100]}")
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
