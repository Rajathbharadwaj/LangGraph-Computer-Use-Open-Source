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
import redis.asyncio as aioredis

# LangGraph SDK client
from langgraph_sdk import get_client

# Database models
from database.models import CronJob, CronJobRun

logger = logging.getLogger(__name__)

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

            # Add workflow or custom prompt
            if cron_job.workflow_id:
                agent_input["workflow"] = cron_job.workflow_id
                logger.info(f"Using workflow: {cron_job.workflow_id}")
            elif cron_job.custom_prompt:
                agent_input["messages"] = [{
                    "role": "user",
                    "content": cron_job.custom_prompt
                }]
                logger.info(f"Using custom prompt (length: {len(cron_job.custom_prompt)})")

            # Merge additional config
            if cron_job.input_config:
                agent_input.update(cron_job.input_config)

            # Execute through LangGraph agent
            logger.info(f"Invoking agent {cron_job.assistant_id} for cron job {cron_job_id}")
            result = await self.client.runs.wait(
                thread_id=thread_id,
                assistant_id=cron_job.assistant_id,
                input=agent_input
            )

            # Mark as completed
            run.status = "completed"
            run.completed_at = datetime.utcnow()
            cron_job.last_run_at = datetime.utcnow()
            db.commit()

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
