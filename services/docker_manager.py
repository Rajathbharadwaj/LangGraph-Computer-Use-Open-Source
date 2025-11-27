"""
Docker container management for per-user browsers
"""
import os
import docker
from typing import Optional, Dict

class DockerBrowserManager:
    """
    Manages Docker containers for user browsers
    One container per user for isolation
    """
    
    def __init__(self):
        docker_host = os.getenv("DOCKER_HOST", "unix:///var/run/docker.sock")
        self.client = docker.DockerClient(base_url=docker_host)
        self.image = os.getenv("DOCKER_BROWSER_IMAGE", "stealth-cua")
        self.network = os.getenv("DOCKER_NETWORK", "xgrowth_network")
        
        # Ensure network exists
        try:
            self.client.networks.get(self.network)
        except docker.errors.NotFound:
            self.client.networks.create(self.network, driver="bridge")
            print(f"✅ Created Docker network: {self.network}")
    
    def get_container_name(self, user_id: str) -> str:
        """Get container name for user"""
        return f"browser-{user_id}"
    
    def container_exists(self, user_id: str) -> bool:
        """Check if user's container exists"""
        container_name = self.get_container_name(user_id)
        try:
            self.client.containers.get(container_name)
            return True
        except docker.errors.NotFound:
            return False
    
    def get_container(self, user_id: str) -> Optional[docker.models.containers.Container]:
        """Get user's container"""
        container_name = self.get_container_name(user_id)
        try:
            return self.client.containers.get(container_name)
        except docker.errors.NotFound:
            return None
    
    def start_container(self, user_id: str) -> Dict[str, any]:
        """
        Start a new browser container for user
        
        Args:
            user_id: User ID
            
        Returns:
            Container info with ports
        """
        container_name = self.get_container_name(user_id)
        
        # Check if already exists
        existing = self.get_container(user_id)
        if existing:
            if existing.status != "running":
                existing.start()
            
            # Get ports
            existing.reload()
            ports = existing.attrs['NetworkSettings']['Ports']
            
            return {
                "container_id": existing.id,
                "container_name": container_name,
                "status": existing.status,
                "browser_port": self._extract_port(ports, '8005/tcp'),
                "vnc_port": self._extract_port(ports, '3000/tcp'),
            }
        
        # Start new container
        print(f"🐳 Starting new browser container for user: {user_id}")
        
        container = self.client.containers.run(
            image=self.image,
            name=container_name,
            detach=True,
            network=self.network,
            ports={
                '8005/tcp': None,  # Random port for browser API
                '3000/tcp': None,  # Random port for VNC
            },
            environment={
                'USER_ID': user_id,
            },
            restart_policy={"Name": "unless-stopped"},
        )
        
        # Get assigned ports
        container.reload()
        ports = container.attrs['NetworkSettings']['Ports']
        
        return {
            "container_id": container.id,
            "container_name": container_name,
            "status": "running",
            "browser_port": self._extract_port(ports, '8005/tcp'),
            "vnc_port": self._extract_port(ports, '3000/tcp'),
        }
    
    def stop_container(self, user_id: str) -> bool:
        """Stop user's container"""
        container = self.get_container(user_id)
        if container:
            container.stop()
            return True
        return False
    
    def remove_container(self, user_id: str) -> bool:
        """Remove user's container"""
        container = self.get_container(user_id)
        if container:
            container.stop()
            container.remove()
            return True
        return False
    
    def _extract_port(self, ports: Dict, port_key: str) -> Optional[int]:
        """Extract host port from Docker port mapping"""
        if port_key in ports and ports[port_key]:
            return int(ports[port_key][0]['HostPort'])
        return None


# Global instance
docker_manager = DockerBrowserManager()

