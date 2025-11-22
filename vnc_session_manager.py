"""
VNC Session Manager - Per-User VNC Container Management

Manages lifecycle of isolated VNC browser sessions using Cloud Run Jobs
"""

import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
import redis.asyncio as aioredis
from google.cloud import run_v2
from google.api_core import exceptions as gcp_exceptions


class VNCSessionManager:
    """Manages per-user VNC browser sessions on Cloud Run Jobs"""

    def __init__(self, redis_host: str = "10.110.183.147", redis_port: int = 6379):
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis: Optional[aioredis.Redis] = None

        # GCP Configuration
        self.project_id = os.getenv("GCP_PROJECT_ID", "parallel-universe-prod")
        self.region = os.getenv("GCP_REGION", "us-central1")
        self.vnc_image = f"gcr.io/{self.project_id}/vnc-browser:latest"

        # Cloud Run Jobs client
        self.jobs_client = run_v2.JobsAsyncClient()

        # Session TTL: 4 hours
        self.session_ttl = 4 * 60 * 60

    async def connect(self):
        """Connect to Redis"""
        if not self.redis:
            self.redis = await aioredis.from_url(
                f"redis://{self.redis_host}:{self.redis_port}",
                encoding="utf-8",
                decode_responses=True
            )

    async def disconnect(self):
        """Disconnect from Redis"""
        if self.redis:
            await self.redis.close()
            self.redis = None

    def _get_session_key(self, user_id: str) -> str:
        """Get Redis key for user's VNC session"""
        return f"vnc:session:{user_id}"

    def _get_job_name(self, user_id: str, session_id: str) -> str:
        """Generate Cloud Run Job name"""
        # Cloud Run job names: lowercase, alphanumeric + hyphens, max 63 chars
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        sanitized_user_id = user_id.replace("_", "-").lower()[:20]
        return f"vnc-{sanitized_user_id}-{timestamp}"

    def _get_job_parent(self) -> str:
        """Get parent path for Cloud Run Job"""
        return f"projects/{self.project_id}/locations/{self.region}"

    async def create_session(self, user_id: str) -> Dict[str, Any]:
        """
        Create a new VNC session for user

        1. Spawn Cloud Run Job with unique name
        2. Store session metadata in Redis
        3. Return VNC WebSocket URL
        """
        await self.connect()

        # Check if user already has an active session
        existing = await self.get_session(user_id)
        if existing and existing.get("status") == "running":
            return existing

        # Generate session ID
        session_id = str(uuid.uuid4())
        job_name = self._get_job_name(user_id, session_id)

        try:
            # Create Cloud Run Job
            job = await self._create_cloud_run_job(job_name, user_id, session_id)

            # Get job URL (will be available once job starts)
            job_url = self._extract_job_url(job)

            # Store session in Redis
            session_data = {
                "session_id": session_id,
                "user_id": user_id,
                "job_name": job_name,
                "url": job_url,
                "created_at": datetime.utcnow().isoformat(),
                "status": "starting"
            }

            await self.redis.setex(
                self._get_session_key(user_id),
                self.session_ttl,
                json.dumps(session_data)
            )

            print(f"✅ Created VNC session for user {user_id}: {session_id}")
            return session_data

        except Exception as e:
            print(f"❌ Failed to create VNC session for {user_id}: {e}")
            raise

    async def _create_cloud_run_job(
        self,
        job_name: str,
        user_id: str,
        session_id: str
    ) -> run_v2.Job:
        """Create Cloud Run Job for VNC container"""

        parent = self._get_job_parent()

        job_config = run_v2.Job(
            name=f"{parent}/jobs/{job_name}",
            template=run_v2.ExecutionTemplate(
                template=run_v2.TaskTemplate(
                    containers=[
                        run_v2.Container(
                            image=self.vnc_image,
                            ports=[run_v2.ContainerPort(container_port=5900)],
                            env=[
                                run_v2.EnvVar(name="USER_ID", value=user_id),
                                run_v2.EnvVar(name="SESSION_ID", value=session_id),
                                run_v2.EnvVar(name="VNC_PASSWORD", value=""),  # No password
                                run_v2.EnvVar(name="DISPLAY_WIDTH", value="1920"),
                                run_v2.EnvVar(name="DISPLAY_HEIGHT", value="1080"),
                            ],
                            resources=run_v2.ResourceRequirements(
                                limits={
                                    "memory": "4Gi",
                                    "cpu": "2"
                                }
                            )
                        )
                    ],
                    timeout="3600s",  # 1 hour max
                    max_retries=0
                )
            ),
            launch_stage=run_v2.LaunchStage.BETA
        )

        # Create the job
        request = run_v2.CreateJobRequest(
            parent=parent,
            job=job_config,
            job_id=job_name
        )

        operation = await self.jobs_client.create_job(request=request)
        job = await operation.result()

        # Run the job execution
        exec_request = run_v2.RunJobRequest(name=job.name)
        await self.jobs_client.run_job(request=exec_request)

        return job

    def _extract_job_url(self, job: run_v2.Job) -> str:
        """Extract WebSocket URL from Cloud Run Job"""
        # The job URL will be available once the execution starts
        # For now, we construct it based on the job name
        # Format: wss://{job-name}-{hash}.{region}.run.app

        # In production, you'd poll the job status to get the actual URL
        # For now, return a placeholder that will be updated when job is running
        job_id = job.name.split("/")[-1]
        return f"wss://{job_id}-starting.{self.region}.run.app"

    async def get_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get current VNC session for user"""
        await self.connect()

        session_key = self._get_session_key(user_id)
        session_json = await self.redis.get(session_key)

        if not session_json:
            return None

        session_data = json.loads(session_json)

        # Update session status by checking Cloud Run Job
        await self._update_session_status(session_data)

        return session_data

    async def _update_session_status(self, session_data: Dict[str, Any]):
        """Update session status by checking Cloud Run Job"""
        try:
            job_name = session_data["job_name"]
            parent = self._get_job_parent()
            full_job_name = f"{parent}/jobs/{job_name}"

            job = await self.jobs_client.get_job(name=full_job_name)

            # Check latest execution status
            if job.latest_created_execution:
                exec_name = job.latest_created_execution.name
                # Get execution details
                # For now, mark as running if job exists
                session_data["status"] = "running"
                session_data["url"] = self._extract_job_url(job)
        except gcp_exceptions.NotFound:
            session_data["status"] = "stopped"
        except Exception as e:
            print(f"⚠️ Error checking job status: {e}")
            # Keep existing status

    async def destroy_session(self, user_id: str) -> bool:
        """
        Terminate VNC session for user

        1. Delete Cloud Run Job
        2. Remove from Redis
        """
        await self.connect()

        session = await self.get_session(user_id)
        if not session:
            return False

        try:
            # Delete Cloud Run Job
            job_name = session["job_name"]
            parent = self._get_job_parent()
            full_job_name = f"{parent}/jobs/{job_name}"

            delete_request = run_v2.DeleteJobRequest(name=full_job_name)
            operation = await self.jobs_client.delete_job(request=delete_request)
            await operation.result()

            # Remove from Redis
            await self.redis.delete(self._get_session_key(user_id))

            print(f"✅ Destroyed VNC session for user {user_id}")
            return True

        except gcp_exceptions.NotFound:
            # Job already deleted, just remove from Redis
            await self.redis.delete(self._get_session_key(user_id))
            return True
        except Exception as e:
            print(f"❌ Failed to destroy VNC session: {e}")
            return False

    async def cleanup_stale_sessions(self):
        """
        Cleanup stale VNC sessions (older than TTL)

        This should be run periodically as a background task
        """
        await self.connect()

        # Scan for all VNC sessions
        cursor = 0
        pattern = "vnc:session:*"

        while True:
            cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)

            for key in keys:
                session_json = await self.redis.get(key)
                if not session_json:
                    continue

                session_data = json.loads(session_json)
                created_at = datetime.fromisoformat(session_data["created_at"])

                # Check if session is older than TTL
                if datetime.utcnow() - created_at > timedelta(seconds=self.session_ttl):
                    user_id = session_data["user_id"]
                    print(f"🧹 Cleaning up stale session for user {user_id}")
                    await self.destroy_session(user_id)

            if cursor == 0:
                break


# Singleton instance
_vnc_manager: Optional[VNCSessionManager] = None


async def get_vnc_manager() -> VNCSessionManager:
    """Get VNC session manager singleton"""
    global _vnc_manager
    if _vnc_manager is None:
        _vnc_manager = VNCSessionManager()
    return _vnc_manager
