"""
Multi-tenant Container Manager
Manages dedicated containers for each user
"""
import docker
import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import random

logger = logging.getLogger(__name__)


class ContainerManager:
    """
    Manages Docker containers for multi-tenant automation
    """

    def __init__(self, docker_host: str = "unix://var/run/docker.sock"):
        """Initialize Docker client"""
        try:
            self.client = docker.DockerClient(base_url=docker_host)
            logger.info(f"✅ Connected to Docker daemon")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Docker: {e}")
            raise

        # Port range for user containers
        self.port_range_start = 9000
        self.port_range_end = 19000

        # Track allocated ports
        self.allocated_ports = set()

    def _get_available_port(self) -> int:
        """Get an available port for new container"""
        # Get all running containers' ports
        running_containers = self.client.containers.list()
        for container in running_containers:
            try:
                port_bindings = container.attrs['NetworkSettings']['Ports']
                for internal_port, bindings in port_bindings.items():
                    if bindings:
                        for binding in bindings:
                            self.allocated_ports.add(int(binding['HostPort']))
            except:
                pass

        # Find available port
        for port in range(self.port_range_start, self.port_range_end):
            if port not in self.allocated_ports:
                self.allocated_ports.add(port)
                return port

        raise Exception("No available ports in range")

    async def create_user_container(
        self,
        user_id: str,
        plan: str = "starter",
        anthropic_api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a dedicated container for user

        Args:
            user_id: Clerk user ID
            plan: User's subscription plan (starter, pro, agency)
            anthropic_api_key: User's API key (or use system key)

        Returns:
            Container info dict
        """
        container_name = f"xgrowth-user-{user_id[:8]}"

        # Check if container already exists
        try:
            existing = self.client.containers.get(container_name)
            if existing.status == "running":
                logger.info(f"Container {container_name} already running")
                return await self._get_container_info(existing)
            else:
                # Remove stopped container
                existing.remove(force=True)
        except docker.errors.NotFound:
            pass

        # Get available port
        host_port = self._get_available_port()

        # Resource limits based on plan
        resource_limits = {
            "free": {"memory": "2g", "cpu": "1.0"},
            "starter": {"memory": "4g", "cpu": "2.0"},
            "pro": {"memory": "8g", "cpu": "4.0"},
            "agency": {"memory": "16g", "cpu": "8.0"}
        }
        resources = resource_limits.get(plan, resource_limits["starter"])

        # Environment variables
        environment = {
            "USER_ID": user_id,
            "ANTHROPIC_API_KEY": anthropic_api_key or "sk-ant-xxx",  # Use user's or system key
            "CONTAINER_PORT": "8000",
            "PYTHONUNBUFFERED": "1"
        }

        try:
            logger.info(f"🚀 Creating container for user {user_id[:8]}...")
            logger.info(f"   - Name: {container_name}")
            logger.info(f"   - Port: {host_port} -> 8000")
            logger.info(f"   - Memory: {resources['memory']}, CPU: {resources['cpu']}")

            # Create container
            container = self.client.containers.run(
                image="xgrowth-automation:latest",  # Your Docker image
                name=container_name,
                environment=environment,
                ports={'8000/tcp': host_port},
                detach=True,
                auto_remove=False,
                mem_limit=resources['memory'],
                cpu_quota=int(float(resources['cpu']) * 100000),
                cpu_period=100000,
                restart_policy={"Name": "unless-stopped"},
                labels={
                    "user_id": user_id,
                    "plan": plan,
                    "managed_by": "xgrowth"
                }
            )

            logger.info(f"✅ Container created: {container.id[:12]}")

            # Wait for container to be healthy
            await self._wait_for_health(container, timeout=30)

            return await self._get_container_info(container)

        except Exception as e:
            logger.error(f"❌ Failed to create container: {e}")
            # Clean up port allocation
            self.allocated_ports.discard(host_port)
            raise

    async def _wait_for_health(self, container, timeout: int = 30):
        """Wait for container to be healthy"""
        start_time = datetime.now()

        while (datetime.now() - start_time).seconds < timeout:
            container.reload()

            if container.status == "running":
                # TODO: Add health check endpoint
                logger.info(f"✅ Container {container.name} is healthy")
                return True

            await asyncio.sleep(1)

        raise TimeoutError(f"Container failed to start within {timeout}s")

    async def _get_container_info(self, container) -> Dict[str, Any]:
        """Get container information"""
        container.reload()

        # Get port mapping
        port_bindings = container.attrs['NetworkSettings']['Ports']
        host_port = None
        if '8000/tcp' in port_bindings and port_bindings['8000/tcp']:
            host_port = int(port_bindings['8000/tcp'][0]['HostPort'])

        return {
            "container_id": container.id,
            "container_name": container.name,
            "status": container.status,
            "host_port": host_port,
            "internal_port": 8000,
            "websocket_url": f"ws://localhost:{host_port}/ws" if host_port else None,
            "created_at": container.attrs['Created'],
            "image": container.attrs['Config']['Image']
        }

    async def stop_user_container(self, user_id: str) -> bool:
        """Stop user's container"""
        container_name = f"xgrowth-user-{user_id[:8]}"

        try:
            container = self.client.containers.get(container_name)
            logger.info(f"🛑 Stopping container {container_name}...")

            # Graceful stop
            container.stop(timeout=10)

            # Free up the port
            port_bindings = container.attrs['NetworkSettings']['Ports']
            if '8000/tcp' in port_bindings and port_bindings['8000/tcp']:
                host_port = int(port_bindings['8000/tcp'][0]['HostPort'])
                self.allocated_ports.discard(host_port)

            logger.info(f"✅ Container stopped: {container_name}")
            return True

        except docker.errors.NotFound:
            logger.warning(f"Container {container_name} not found")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to stop container: {e}")
            return False

    async def restart_user_container(self, user_id: str) -> bool:
        """Restart user's container"""
        container_name = f"xgrowth-user-{user_id[:8]}"

        try:
            container = self.client.containers.get(container_name)
            logger.info(f"🔄 Restarting container {container_name}...")
            container.restart(timeout=10)
            logger.info(f"✅ Container restarted: {container_name}")
            return True

        except docker.errors.NotFound:
            logger.warning(f"Container {container_name} not found")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to restart container: {e}")
            return False

    async def remove_user_container(self, user_id: str, force: bool = False) -> bool:
        """Remove user's container"""
        container_name = f"xgrowth-user-{user_id[:8]}"

        try:
            container = self.client.containers.get(container_name)
            logger.info(f"🗑️  Removing container {container_name}...")

            # Stop first if running
            if container.status == "running" and not force:
                container.stop(timeout=10)

            # Remove
            container.remove(force=force)

            # Free up port
            port_bindings = container.attrs['NetworkSettings']['Ports']
            if '8000/tcp' in port_bindings and port_bindings['8000/tcp']:
                host_port = int(port_bindings['8000/tcp'][0]['HostPort'])
                self.allocated_ports.discard(host_port)

            logger.info(f"✅ Container removed: {container_name}")
            return True

        except docker.errors.NotFound:
            logger.warning(f"Container {container_name} not found")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to remove container: {e}")
            return False

    async def get_container_status(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get container status"""
        container_name = f"xgrowth-user-{user_id[:8]}"

        try:
            container = self.client.containers.get(container_name)
            return await self._get_container_info(container)
        except docker.errors.NotFound:
            return None

    async def get_container_logs(self, user_id: str, tail: int = 100) -> str:
        """Get container logs"""
        container_name = f"xgrowth-user-{user_id[:8]}"

        try:
            container = self.client.containers.get(container_name)
            logs = container.logs(tail=tail, timestamps=True)
            return logs.decode('utf-8')
        except docker.errors.NotFound:
            return "Container not found"
        except Exception as e:
            return f"Error getting logs: {e}"

    async def list_all_containers(self) -> list:
        """List all user containers"""
        containers = self.client.containers.list(
            all=True,
            filters={"label": "managed_by=xgrowth"}
        )

        result = []
        for container in containers:
            result.append({
                "container_id": container.id[:12],
                "name": container.name,
                "status": container.status,
                "user_id": container.labels.get("user_id"),
                "plan": container.labels.get("plan"),
                "created": container.attrs['Created']
            })

        return result

    async def cleanup_stopped_containers(self):
        """Remove all stopped containers"""
        containers = self.client.containers.list(
            all=True,
            filters={
                "status": "exited",
                "label": "managed_by=xgrowth"
            }
        )

        for container in containers:
            try:
                logger.info(f"🧹 Cleaning up stopped container: {container.name}")
                container.remove()
            except Exception as e:
                logger.error(f"Failed to remove {container.name}: {e}")


# Singleton instance
_container_manager = None


def get_container_manager() -> ContainerManager:
    """Get or create container manager instance"""
    global _container_manager
    if _container_manager is None:
        _container_manager = ContainerManager()
    return _container_manager
