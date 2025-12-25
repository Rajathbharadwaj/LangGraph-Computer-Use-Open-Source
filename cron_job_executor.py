"""
Cron Job Executor
Manages recurring workflow executions using APScheduler.
Executes workflows/prompts on a cron schedule through the Deep Agent.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from typing import Dict, Any, Optional
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

# Workflow prompt generator
from x_growth_workflows import get_workflow_prompt

# Database models
from database.models import CronJob, CronJobRun

# Billing service for credit tracking
from services.billing_service import BillingService
from services.stripe_service import AGENT_SESSION_COSTS, CREDIT_COSTS

logger = logging.getLogger(__name__)

# Extension backend URL for cookie fetching
EXTENSION_BACKEND_URL = os.environ.get("EXTENSION_BACKEND_URL", "http://127.0.0.1:8001")

# Database setup
DATABASE_URL = os.getenv("POSTGRES_URI") or os.getenv("DATABASE_URL") or "postgresql://postgres:password@localhost:5433/xgrowth"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# LangGraph server URL
LANGGRAPH_URL = os.getenv("LANGGRAPH_URL", "http://localhost:8124")


class CronJobExecutor:
    """Manages recurring cron job execution through LangGraph Deep Agent"""

    def __init__(self, langgraph_url: str = LANGGRAPH_URL):
        self.scheduler = AsyncIOScheduler(timezone='UTC')
        self.scheduled_jobs = {}  # {job_id: job_info}
        self.is_running = False
        self.langgraph_url = langgraph_url
        self.client = None
        self.redis_client = None
        self.redis_host = os.getenv("REDIS_HOST", "10.110.183.147")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))

    async def initialize(self):
        """Initialize executor and load active cron jobs from database"""
        try:
            # Initialize LangGraph SDK client
            self.client = get_client(url=self.langgraph_url)

            # Initialize VNC session manager
            self.vnc_manager = await get_vnc_manager()

            # Initialize Redis client for distributed locks
            try:
                self.redis_client = await aioredis.from_url(
                    f"redis://{self.redis_host}:{self.redis_port}",
                    encoding="utf-8",
                    decode_responses=True
                )
                await self.redis_client.ping()
                logger.info(f"✅ Connected to Redis at {self.redis_host}:{self.redis_port}")
            except Exception as redis_err:
                logger.warning(f"⚠️ Redis connection failed: {redis_err}. Concurrent execution protection disabled.")
                self.redis_client = None

            # Start scheduler
            self.scheduler.start()
            self.is_running = True

            # Load active cron jobs from database
            await self.load_active_cron_jobs()

            logger.info(f"✅ CronJobExecutor initialized with {len(self.scheduled_jobs)} active jobs")
        except Exception as e:
            logger.error(f"❌ Failed to initialize CronJobExecutor: {e}")
            raise

    async def _get_user_vnc_url(self, user_id: str) -> Optional[str]:
        """
        Get the VNC URL for a user's browser session.
        Looks up from Redis first, then Cloud Run if not cached.
        Will auto-create a session if none exists.
        """
        try:
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
                expires_value = cookie.get("expirationDate", -1)
                if expires_value and expires_value != -1:
                    expires_value = int(expires_value)
                else:
                    expires_value = -1

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

    async def load_active_cron_jobs(self):
        """Load all active cron jobs from database and schedule them"""
        db = SessionLocal()
        try:
            active_jobs = db.query(CronJob).filter(CronJob.is_active == True).all()
            logger.info(f"Loading {len(active_jobs)} active cron jobs from database")

            for cron_job in active_jobs:
                try:
                    self.schedule_cron_job(cron_job)
                    logger.info(f"Scheduled cron job: {cron_job.name} (ID: {cron_job.id})")
                except Exception as e:
                    logger.error(f"Failed to schedule cron job {cron_job.id}: {e}")
        finally:
            db.close()

    def schedule_cron_job(self, cron_job: CronJob):
        """Schedule a recurring cron job using APScheduler"""
        job_id = f"cron_{cron_job.id}"

        # Parse cron expression (e.g., "0 9 * * *")
        # Format: minute hour day month day_of_week
        parts = cron_job.schedule.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {cron_job.schedule}. Expected format: 'minute hour day month day_of_week'")

        # Create async wrapper for execution
        async def execute_wrapper():
            await self._execute_cron_job(cron_job.id)

        # Use CronTrigger for recurring execution
        job = self.scheduler.add_job(
            func=execute_wrapper,
            trigger=CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
                timezone=cron_job.timezone
            ),
            id=job_id,
            replace_existing=True
        )

        self.scheduled_jobs[job_id] = {
            "cron_job_id": cron_job.id,
            "name": cron_job.name,
            "schedule": cron_job.schedule,
            "job": job
        }

        logger.info(f"Scheduled cron job '{cron_job.name}' with schedule: {cron_job.schedule}")

    async def _acquire_lock(self, user_id: str, timeout: int = 300) -> bool:
        """
        Acquire distributed lock for user to prevent concurrent executions

        Args:
            user_id: User ID to lock
            timeout: Lock timeout in seconds (default 5 minutes)

        Returns:
            True if lock acquired, False otherwise
        """
        if not self.redis_client:
            # Redis not available, allow execution (no lock protection)
            return True

        lock_key = f"cron:lock:user:{user_id}"

        try:
            # Try to set lock with NX (only if not exists) and EX (expiry)
            acquired = await self.redis_client.set(lock_key, "locked", nx=True, ex=timeout)
            return bool(acquired)
        except Exception as e:
            logger.warning(f"⚠️ Failed to acquire lock for user {user_id}: {e}")
            # If Redis fails, allow execution (graceful degradation)
            return True

    async def _release_lock(self, user_id: str):
        """Release distributed lock for user"""
        if not self.redis_client:
            return

        lock_key = f"cron:lock:user:{user_id}"

        try:
            await self.redis_client.delete(lock_key)
        except Exception as e:
            logger.warning(f"⚠️ Failed to release lock for user {user_id}: {e}")

    async def _execute_cron_job(self, cron_job_id: int):
        """Execute a cron job by invoking the LangGraph agent"""
        db = SessionLocal()
        run = None
        user_id = None
        lock_acquired = False

        try:
            # Get cron job details
            cron_job = db.query(CronJob).filter(CronJob.id == cron_job_id).first()
            if not cron_job:
                logger.error(f"Cron job {cron_job_id} not found")
                return

            if not cron_job.is_active:
                logger.info(f"Cron job {cron_job_id} is inactive, skipping execution")
                return

            user_id = cron_job.user_id

            # Try to acquire lock for this user
            lock_acquired = await self._acquire_lock(user_id)

            if not lock_acquired:
                logger.warning(f"⏭️ Skipping cron job {cron_job_id} - another job already running for user {user_id}")
                return

            logger.info(f"🔄 Executing cron job: {cron_job.name} (ID: {cron_job_id}) [Lock acquired]")

            # Check if user has enough credits
            billing = BillingService(db)
            min_credits = AGENT_SESSION_COSTS.get("x_growth", 10)
            has_credits, reason = billing.check_credits(user_id, min_credits)
            if not has_credits:
                logger.warning(f"⚠️ Skipping cron job {cron_job_id} - user {user_id} has insufficient credits: {reason}")
                await self._release_lock(user_id)
                return

            session_start_time = datetime.utcnow()

            # Create execution record
            run = CronJobRun(
                cron_job_id=cron_job_id,
                status="running",
                started_at=datetime.utcnow()
            )
            db.add(run)
            db.commit()
            db.refresh(run)

            # Create LangGraph thread
            thread = await self.client.threads.create()
            thread_id = thread["thread_id"]
            run.thread_id = thread_id
            db.commit()

            logger.info(f"Created thread {thread_id} for cron job {cron_job_id}")

            # Prepare agent input
            agent_input = {
                "user_id": cron_job.user_id,
                "cron_job_id": cron_job_id
            }

            # Add workflow or custom prompt - convert workflow ID to actual prompt
            if cron_job.workflow_id:
                # Convert workflow ID to full prompt using get_workflow_prompt
                try:
                    workflow_prompt = get_workflow_prompt(cron_job.workflow_id)
                    agent_input["messages"] = [{
                        "role": "user",
                        "content": workflow_prompt
                    }]
                    logger.info(f"Using workflow: {cron_job.workflow_id} (converted to prompt, length: {len(workflow_prompt)})")
                except Exception as e:
                    logger.error(f"❌ Failed to load workflow {cron_job.workflow_id}: {e}")
                    raise ValueError(f"Failed to load workflow {cron_job.workflow_id}: {e}")
            elif cron_job.custom_prompt:
                agent_input["messages"] = [{
                    "role": "user",
                    "content": cron_job.custom_prompt
                }]
                logger.info(f"Using custom prompt (length: {len(cron_job.custom_prompt)})")
            else:
                # This should NEVER happen due to API validation, but fail loudly if it does
                error_msg = f"Invalid cron job {cron_job_id}: missing both workflow_id and custom_prompt"
                logger.error(f"❌ {error_msg}")
                raise ValueError(error_msg)

            # Merge additional config
            if cron_job.input_config:
                agent_input.update(cron_job.input_config)

            # Get or create VNC session for the user
            logger.info(f"🖥️ Getting VNC session for user {user_id}...")
            vnc_url = await self._get_user_vnc_url(user_id)

            if not vnc_url:
                raise Exception(f"Could not get VNC session for user {user_id}")

            logger.info(f"✅ VNC URL: {vnc_url}")

            # Inject cookies to ensure authenticated session
            logger.info(f"🔐 Injecting cookies for user {user_id}...")
            cookie_result = await self._inject_cookies_to_vnc(user_id, vnc_url)

            if not cookie_result:
                logger.warning(f"⚠️ Cookie injection failed, but attempting to continue...")

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
                        cua_port = "443"
                except Exception as e:
                    logger.warning(f"⚠️ Could not parse VNC URL: {e}")

            logger.info(f"🌐 CUA Host: {cua_host}, Port: {cua_port}")

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

            # Execute through LangGraph agent
            logger.info(f"🤖 Invoking agent {cron_job.assistant_id} for cron job {cron_job_id} with VNC URL: {vnc_url}")
            result = await self.client.runs.wait(
                thread_id=thread_id,
                assistant_id=cron_job.assistant_id,
                input=agent_input,
                config=config  # Now passing the config with cua_url!
            )

            # Mark as completed
            run.status = "completed"
            run.completed_at = datetime.utcnow()
            cron_job.last_run_at = datetime.utcnow()
            db.commit()

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
                        agent_type="x_growth",
                        description=f"Cron job: {cron_job.name[:40]}"
                    )
                    logger.info(f"💳 Charged {billing_result['credits_charged']} credits "
                                f"(${billing_result['actual_cost']:.2f} actual) for cron job {cron_job_id}")
                else:
                    # Fallback: Use fixed estimate if no run_id
                    logger.warning(f"⚠️ No run_id available for cron job {cron_job_id}, using fallback billing")
                    session_duration_minutes = (datetime.utcnow() - session_start_time).total_seconds() / 60
                    base_cost = AGENT_SESSION_COSTS.get("x_growth", 10)
                    computer_use_cost = int(session_duration_minutes * CREDIT_COSTS.get("computer_use_minute", 5)) if vnc_url else 0
                    total_credits = base_cost + computer_use_cost

                    billing.consume_credits(
                        user_id=user_id,
                        credits=total_credits,
                        description=f"Cron job: {cron_job.name[:40]}",
                        agent_type="x_growth"
                    )
                    logger.info(f"💳 Fallback billing: {total_credits} credits for cron job {cron_job_id}")

            except Exception as credit_error:
                logger.warning(f"⚠️ Failed to consume credits for cron job {cron_job_id}: {credit_error}")

            logger.info(f"✅ Completed cron job: {cron_job.name} (ID: {cron_job_id})")

        except Exception as e:
            logger.error(f"❌ Error executing cron job {cron_job_id}: {e}", exc_info=True)

            # Mark as failed
            if run:
                run.status = "failed"
                run.error_message = str(e)
                run.completed_at = datetime.utcnow()
                db.commit()

                # Check if error is authentication-related
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in ['auth', 'cookie', 'login', 'session', 'unauthorized']):
                    # Check for repeated auth failures (3+ in a row)
                    recent_runs = db.query(CronJobRun).filter(
                        CronJobRun.cron_job_id == cron_job_id
                    ).order_by(CronJobRun.started_at.desc()).limit(3).all()

                    if len(recent_runs) >= 3 and all(r.status == "failed" for r in recent_runs):
                        # Pause the cron job and mark X account as disconnected
                        cron_job.is_active = False
                        logger.warning(f"⚠️ Paused cron job {cron_job_id} due to repeated auth failures")

                        # TODO: Send email notification to user
                        # email.send(user_id, "Reconnect your X account", "Your scheduled automation has been paused...")
                        db.commit()
        finally:
            # Always release lock, even on error
            if lock_acquired and user_id:
                await self._release_lock(user_id)
                logger.info(f"🔓 Released lock for user {user_id}")

            db.close()

    def cancel_cron_job(self, cron_job_id: int):
        """Cancel a scheduled cron job"""
        job_id = f"cron_{cron_job_id}"

        if job_id in self.scheduled_jobs:
            try:
                self.scheduler.remove_job(job_id)
                del self.scheduled_jobs[job_id]
                logger.info(f"Cancelled cron job: {job_id}")
            except Exception as e:
                logger.error(f"Failed to cancel cron job {job_id}: {e}")
        else:
            logger.warning(f"Cron job {job_id} not found in scheduler")

    def get_scheduled_jobs(self) -> Dict[str, Dict[str, Any]]:
        """Get all currently scheduled jobs"""
        return self.scheduled_jobs

    async def shutdown(self):
        """Shutdown the executor gracefully"""
        if self.is_running:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("CronJobExecutor shut down")


# Global executor instance
_executor_instance: Optional[CronJobExecutor] = None


async def get_cron_executor() -> CronJobExecutor:
    """Get or create the global cron executor instance"""
    global _executor_instance

    if _executor_instance is None:
        _executor_instance = CronJobExecutor(langgraph_url=LANGGRAPH_URL)
        await _executor_instance.initialize()

    return _executor_instance
