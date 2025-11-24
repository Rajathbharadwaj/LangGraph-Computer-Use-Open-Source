"""
VNC Session Manager - Per-User VNC Container Management

Manages lifecycle of isolated VNC browser sessions using Cloud Run Services.
Each user gets their own dedicated Cloud Run Service with VNC access.

Architecture (like Steel Browser):
- One Cloud Run Service per user
- Service scales to 0 when idle (cost efficient)
- Service URL provides WebSocket access for VNC
- Cookies injected at service startup
"""

import asyncio
import json
import os
import uuid
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List
import redis.asyncio as aioredis
from google.cloud import run_v2
from google.api_core import exceptions as gcp_exceptions


class VNCSessionManager:
    """
    Manages per-user VNC browser sessions on Cloud Run Services.

    Unlike Jobs, Services provide:
    - Persistent URLs for WebSocket connections
    - Auto-scaling to 0 when idle
    - Immediate availability for subsequent requests
    """

    def __init__(self, redis_host: str = None, redis_port: int = 6379):
        # Redis config - use environment variable or default
        self.redis_host = redis_host or os.getenv("REDIS_HOST", "10.110.183.147")
        self.redis_port = redis_port
        self.redis: Optional[aioredis.Redis] = None

        # GCP Configuration
        self.project_id = os.getenv("GCP_PROJECT_ID", "parallel-universe-prod")
        self.region = os.getenv("GCP_REGION", "us-central1")
        self.vnc_image = os.getenv(
            "VNC_BROWSER_IMAGE",
            f"gcr.io/{self.project_id}/vnc-browser:latest"
        )

        # Cloud Run Services client
        self.services_client = run_v2.ServicesAsyncClient()

        # Session TTL: 4 hours (in Redis)
        self.session_ttl = 4 * 60 * 60

        # Service idle timeout: 15 minutes (Cloud Run will scale to 0)
        self.service_timeout = 15 * 60

    async def connect(self):
        """Connect to Redis"""
        if not self.redis:
            try:
                self.redis = await aioredis.from_url(
                    f"redis://{self.redis_host}:{self.redis_port}",
                    encoding="utf-8",
                    decode_responses=True
                )
                # Test connection
                await self.redis.ping()
                print(f"✅ Connected to Redis at {self.redis_host}:{self.redis_port}")
            except Exception as e:
                print(f"⚠️ Redis connection failed: {e}")
                self.redis = None

    async def disconnect(self):
        """Disconnect from Redis"""
        if self.redis:
            await self.redis.close()
            self.redis = None

    def _get_session_key(self, user_id: str) -> str:
        """Get Redis key for user's VNC session"""
        return f"vnc:session:{user_id}"

    def _get_service_name(self, user_id: str) -> str:
        """
        Generate Cloud Run Service name for user.

        Requirements:
        - Lowercase letters, numbers, hyphens only
        - Must start with letter
        - Max 63 characters
        - Must be unique per user
        """
        # Create a short hash of the user_id for uniqueness
        user_hash = hashlib.sha256(user_id.encode()).hexdigest()[:8]

        # Sanitize user_id: lowercase, replace non-alphanumeric with hyphen
        sanitized = ''.join(c if c.isalnum() else '-' for c in user_id.lower())
        sanitized = sanitized[:20]  # Limit length

        # Ensure starts with letter
        if not sanitized[0].isalpha():
            sanitized = 'u' + sanitized

        return f"vnc-{sanitized}-{user_hash}"

    def _get_service_parent(self) -> str:
        """Get parent path for Cloud Run Service"""
        return f"projects/{self.project_id}/locations/{self.region}"

    async def get_or_create_session(self, user_id: str, cookies: List[Dict] = None) -> Dict[str, Any]:
        """
        Get existing VNC session or create new one.

        This is the main entry point - ensures user has an active VNC session.

        Args:
            user_id: Unique user identifier
            cookies: Optional list of cookies to inject (for X.com session)

        Returns:
            Session data including VNC WebSocket URL
        """
        await self.connect()

        # Check for existing session in Redis
        existing = await self.get_session(user_id)

        if existing and existing.get("status") == "running":
            print(f"✅ Found existing VNC session for user {user_id}")
            return existing

        # Create new session
        return await self.create_session(user_id, cookies)

    async def create_session(self, user_id: str, cookies: List[Dict] = None) -> Dict[str, Any]:
        """
        Create a new VNC session for user.

        1. Create/update Cloud Run Service for user
        2. Wait for service to be ready
        3. Store session metadata in Redis
        4. Return VNC WebSocket URL
        """
        await self.connect()

        session_id = str(uuid.uuid4())
        service_name = self._get_service_name(user_id)

        try:
            # Check if service already exists
            service_exists = await self._service_exists(service_name)

            if service_exists:
                print(f"🔄 Updating existing service for user {user_id}")
                service = await self._update_service(service_name, user_id, session_id, cookies)
            else:
                print(f"🚀 Creating new service for user {user_id}")
                service = await self._create_service(service_name, user_id, session_id, cookies)

            # Get service URL
            service_url = await self._get_service_url(service_name)

            if not service_url:
                raise Exception("Service created but URL not available")

            # Convert HTTPS URL to WSS for VNC
            vnc_url = service_url.replace("https://", "wss://")

            # Store session in Redis
            session_data = {
                "session_id": session_id,
                "user_id": user_id,
                "service_name": service_name,
                "url": vnc_url,
                "https_url": service_url,
                "created_at": datetime.utcnow().isoformat(),
                "status": "running"
            }

            if self.redis:
                await self.redis.setex(
                    self._get_session_key(user_id),
                    self.session_ttl,
                    json.dumps(session_data)
                )

            print(f"✅ VNC session ready for user {user_id}: {vnc_url}")
            return session_data

        except Exception as e:
            print(f"❌ Failed to create VNC session for {user_id}: {e}")
            raise

    async def _service_exists(self, service_name: str) -> bool:
        """Check if Cloud Run Service exists"""
        try:
            parent = self._get_service_parent()
            full_name = f"{parent}/services/{service_name}"
            await self.services_client.get_service(name=full_name)
            return True
        except gcp_exceptions.NotFound:
            return False
        except Exception as e:
            print(f"⚠️ Error checking service existence: {e}")
            return False

    async def _create_service(
        self,
        service_name: str,
        user_id: str,
        session_id: str,
        cookies: List[Dict] = None
    ) -> run_v2.Service:
        """Create new Cloud Run Service for VNC container"""

        parent = self._get_service_parent()

        # Prepare environment variables
        env_vars = [
            run_v2.EnvVar(name="USER_ID", value=user_id),
            run_v2.EnvVar(name="SESSION_ID", value=session_id),
            run_v2.EnvVar(name="VNC_PASSWORD", value=""),  # No password for internal use
            run_v2.EnvVar(name="DISPLAY_WIDTH", value="1280"),
            run_v2.EnvVar(name="DISPLAY_HEIGHT", value="720"),
        ]

        # Add cookies as JSON environment variable if provided
        if cookies:
            env_vars.append(
                run_v2.EnvVar(name="X_COOKIES", value=json.dumps(cookies))
            )

        service_config = run_v2.Service(
            template=run_v2.RevisionTemplate(
                containers=[
                    run_v2.Container(
                        image=self.vnc_image,
                        ports=[
                            run_v2.ContainerPort(container_port=6080, name="http1")  # noVNC WebSocket
                        ],
                        env=env_vars,
                        resources=run_v2.ResourceRequirements(
                            limits={
                                "memory": "4Gi",
                                "cpu": "2"
                            }
                        ),
                        # Startup probe to ensure VNC is ready
                        startup_probe=run_v2.Probe(
                            http_get=run_v2.HTTPGetAction(
                                path="/",
                                port=6080
                            ),
                            initial_delay_seconds=5,
                            timeout_seconds=3,
                            period_seconds=5,
                            failure_threshold=10
                        )
                    )
                ],
                # Scale to 0 when idle, max 1 instance per user
                scaling=run_v2.RevisionScaling(
                    min_instance_count=0,
                    max_instance_count=1
                ),
                # Timeout settings
                timeout="3600s"  # 1 hour max request duration
                # NOTE: No VPC connector - VNC services need direct internet access for X.com
            ),
            # Allow unauthenticated access (authentication handled at app level)
            ingress=run_v2.IngressTraffic.INGRESS_TRAFFIC_ALL
        )

        request = run_v2.CreateServiceRequest(
            parent=parent,
            service=service_config,
            service_id=service_name
        )

        print(f"📦 Creating Cloud Run Service: {service_name}")
        operation = await self.services_client.create_service(request=request)
        service = await operation.result()

        # Set IAM policy to allow unauthenticated access
        await self._set_public_access(service_name)

        print(f"✅ Service created: {service_name}")
        return service

    async def _update_service(
        self,
        service_name: str,
        user_id: str,
        session_id: str,
        cookies: List[Dict] = None
    ) -> run_v2.Service:
        """Update existing Cloud Run Service with new session"""

        parent = self._get_service_parent()
        full_name = f"{parent}/services/{service_name}"

        # Get existing service
        service = await self.services_client.get_service(name=full_name)

        # Update environment variables
        env_vars = [
            run_v2.EnvVar(name="USER_ID", value=user_id),
            run_v2.EnvVar(name="SESSION_ID", value=session_id),
            run_v2.EnvVar(name="VNC_PASSWORD", value=""),
            run_v2.EnvVar(name="DISPLAY_WIDTH", value="1280"),
            run_v2.EnvVar(name="DISPLAY_HEIGHT", value="720"),
        ]

        if cookies:
            env_vars.append(
                run_v2.EnvVar(name="X_COOKIES", value=json.dumps(cookies))
            )

        # Update container env vars
        if service.template.containers:
            service.template.containers[0].env = env_vars

        request = run_v2.UpdateServiceRequest(service=service)

        print(f"🔄 Updating Cloud Run Service: {service_name}")
        operation = await self.services_client.update_service(request=request)
        updated_service = await operation.result()

        print(f"✅ Service updated: {service_name}")
        return updated_service

    async def _set_public_access(self, service_name: str):
        """Set IAM policy to allow unauthenticated access to service"""
        try:
            from google.iam.v1 import iam_policy_pb2, policy_pb2

            parent = self._get_service_parent()
            resource = f"{parent}/services/{service_name}"

            # Create policy allowing allUsers
            policy = policy_pb2.Policy(
                bindings=[
                    policy_pb2.Binding(
                        role="roles/run.invoker",
                        members=["allUsers"]
                    )
                ]
            )

            request = iam_policy_pb2.SetIamPolicyRequest(
                resource=resource,
                policy=policy
            )

            await self.services_client.set_iam_policy(request=request)
            print(f"✅ Public access enabled for {service_name}")

        except Exception as e:
            print(f"⚠️ Failed to set public access (service may still work): {e}")

    async def _get_service_url(self, service_name: str) -> Optional[str]:
        """Get the URL of a Cloud Run Service"""
        try:
            parent = self._get_service_parent()
            full_name = f"{parent}/services/{service_name}"

            # Poll until service is ready (max 60 seconds)
            for _ in range(12):
                service = await self.services_client.get_service(name=full_name)

                if service.uri:
                    return service.uri

                print(f"⏳ Waiting for service URL...")
                await asyncio.sleep(5)

            return None

        except Exception as e:
            print(f"❌ Error getting service URL: {e}")
            return None

    async def get_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get current VNC session for user"""
        await self.connect()

        if not self.redis:
            # Redis not available, try to get service directly
            return await self._get_session_from_service(user_id)

        session_key = self._get_session_key(user_id)
        session_json = await self.redis.get(session_key)

        if not session_json:
            # Check if service exists even without Redis entry
            return await self._get_session_from_service(user_id)

        session_data = json.loads(session_json)

        # Verify service is still running
        service_name = session_data.get("service_name")
        if service_name:
            exists = await self._service_exists(service_name)
            if not exists:
                session_data["status"] = "stopped"
                await self.redis.delete(session_key)
                return None

        return session_data

    async def _get_session_from_service(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get session info directly from Cloud Run Service"""
        service_name = self._get_service_name(user_id)

        if not await self._service_exists(service_name):
            return None

        service_url = await self._get_service_url(service_name)
        if not service_url:
            return None

        vnc_url = service_url.replace("https://", "wss://")

        return {
            "session_id": "recovered",
            "user_id": user_id,
            "service_name": service_name,
            "url": vnc_url,
            "https_url": service_url,
            "status": "running"
        }

    async def destroy_session(self, user_id: str) -> bool:
        """
        Terminate VNC session for user.

        1. Delete Cloud Run Service
        2. Remove from Redis
        """
        await self.connect()

        session = await self.get_session(user_id)
        service_name = session.get("service_name") if session else self._get_service_name(user_id)

        try:
            # Delete Cloud Run Service
            parent = self._get_service_parent()
            full_name = f"{parent}/services/{service_name}"

            request = run_v2.DeleteServiceRequest(name=full_name)
            operation = await self.services_client.delete_service(request=request)
            await operation.result()

            print(f"✅ Deleted Cloud Run Service: {service_name}")

        except gcp_exceptions.NotFound:
            print(f"⚠️ Service already deleted: {service_name}")
        except Exception as e:
            print(f"❌ Failed to delete service: {e}")

        # Remove from Redis
        if self.redis:
            await self.redis.delete(self._get_session_key(user_id))

        print(f"✅ Destroyed VNC session for user {user_id}")
        return True

    async def cleanup_stale_sessions(self):
        """
        Cleanup stale VNC sessions.

        This should be run periodically as a background task.
        Cloud Run Services auto-scale to 0, but we should clean up
        services that haven't been used for extended periods.
        """
        await self.connect()

        if not self.redis:
            print("⚠️ Redis not available, skipping cleanup")
            return

        cursor = 0
        pattern = "vnc:session:*"
        cleaned = 0

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
                    cleaned += 1

            if cursor == 0:
                break

        print(f"🧹 Cleanup complete. Removed {cleaned} stale sessions.")

    async def list_all_sessions(self) -> List[Dict[str, Any]]:
        """List all active VNC sessions (for admin purposes)"""
        await self.connect()

        sessions = []

        if self.redis:
            cursor = 0
            pattern = "vnc:session:*"

            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)

                for key in keys:
                    session_json = await self.redis.get(key)
                    if session_json:
                        sessions.append(json.loads(session_json))

                if cursor == 0:
                    break

        return sessions


# Singleton instance
_vnc_manager: Optional[VNCSessionManager] = None


async def get_vnc_manager() -> VNCSessionManager:
    """Get VNC session manager singleton"""
    global _vnc_manager
    if _vnc_manager is None:
        _vnc_manager = VNCSessionManager()
    return _vnc_manager


# Convenience functions
async def get_user_vnc_session(user_id: str, cookies: List[Dict] = None) -> Dict[str, Any]:
    """Get or create VNC session for user - main entry point"""
    manager = await get_vnc_manager()
    return await manager.get_or_create_session(user_id, cookies)


async def destroy_user_vnc_session(user_id: str) -> bool:
    """Destroy VNC session for user"""
    manager = await get_vnc_manager()
    return await manager.destroy_session(user_id)
