"""Test APScheduler with async functions"""
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_job(job_id: str):
    """Test async job"""
    logger.info(f"🚀 Executing job: {job_id}")
    await asyncio.sleep(1)
    logger.info(f"✅ Job {job_id} completed")

async def main():
    scheduler = AsyncIOScheduler()
    scheduler.start()
    logger.info("✅ Scheduler started")

    # Schedule a job for 5 seconds from now
    run_time = datetime.now() + timedelta(seconds=5)

    # Method 1: Direct async function
    async def execute_wrapper():
        await test_job("test_1")

    scheduler.add_job(
        func=execute_wrapper,
        trigger=DateTrigger(run_date=run_time),
        id="test_job_1"
    )

    logger.info(f"📅 Job scheduled for {run_time}")
    logger.info(f"📊 Active jobs: {scheduler.get_jobs()}")

    # Wait for execution
    await asyncio.sleep(10)

    logger.info("✅ Test complete")
    scheduler.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
