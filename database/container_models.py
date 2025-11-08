"""
Container models for multi-tenant architecture
Each user gets their own isolated container
"""
from sqlalchemy import Column, String, Integer, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class UserContainer(Base):
    """
    User's dedicated automation container
    """
    __tablename__ = "user_containers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)

    # Container info
    container_id = Column(String, unique=True)  # Docker container ID
    container_name = Column(String, unique=True)  # e.g., "user-clerk_xxx"

    # Network info
    host_port = Column(Integer, unique=True)  # Port on host machine
    internal_port = Column(Integer, default=8000)  # Port inside container
    websocket_url = Column(String)  # Full WebSocket URL

    # Status
    status = Column(String, default="creating")  # creating, running, stopped, failed
    is_active = Column(Boolean, default=True)

    # Resources (based on plan)
    memory_limit = Column(String, default="4g")  # "4g", "8g", "16g"
    cpu_limit = Column(String, default="2.0")  # "2.0", "4.0"

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    stopped_at = Column(DateTime)
    last_health_check = Column(DateTime)

    # Stats
    uptime_seconds = Column(Integer, default=0)
    total_actions = Column(Integer, default=0)

    # Metadata
    config = Column(JSON)  # Container-specific config

    # Relationships
    user = relationship("User", backref="container")


class ContainerLog(Base):
    """
    Container activity logs
    """
    __tablename__ = "container_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    container_id = Column(Integer, ForeignKey("user_containers.id"), nullable=False)

    # Log info
    level = Column(String, nullable=False)  # info, warning, error, debug
    message = Column(String, nullable=False)
    details = Column(JSON)

    # Timestamp
    logged_at = Column(DateTime, default=datetime.utcnow)


class ContainerAction(Base):
    """
    Actions performed by container (likes, comments, follows)
    """
    __tablename__ = "container_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    container_id = Column(Integer, ForeignKey("user_containers.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Action details
    action_type = Column(String, nullable=False)  # like, comment, follow, unfollow
    target = Column(String)  # username or post URL
    success = Column(Boolean, default=True)

    # Metadata
    details = Column(JSON)  # Extra info about the action

    # Timestamp
    performed_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User")
