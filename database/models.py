"""
Database models for X Growth Automation
"""
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class User(Base):
    """
    User account (authenticated via Clerk)
    """
    __tablename__ = "users"
    
    id = Column(String, primary_key=True)  # Clerk user ID
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Subscription info
    plan = Column(String, default="free")  # free, pro, enterprise
    is_active = Column(Boolean, default=True)
    
    # Relationships
    x_accounts = relationship("XAccount", back_populates="user", cascade="all, delete-orphan")
    api_usage = relationship("APIUsage", back_populates="user", cascade="all, delete-orphan")


class XAccount(Base):
    """
    Connected X (Twitter) accounts
    """
    __tablename__ = "x_accounts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    
    # X account info
    username = Column(String, nullable=False)
    display_name = Column(String)
    profile_image_url = Column(String)
    
    # Status
    is_connected = Column(Boolean, default=True)
    last_synced_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="x_accounts")
    cookies = relationship("UserCookies", back_populates="x_account", cascade="all, delete-orphan")
    posts = relationship("UserPost", back_populates="x_account", cascade="all, delete-orphan")


class UserCookies(Base):
    """
    Encrypted X cookies for each account
    """
    __tablename__ = "user_cookies"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    x_account_id = Column(Integer, ForeignKey("x_accounts.id"), nullable=False)
    
    # Encrypted cookie data
    encrypted_cookies = Column(Text, nullable=False)
    
    # Metadata
    captured_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    
    # Relationships
    x_account = relationship("XAccount", back_populates="cookies")


class UserPost(Base):
    """
    User's X posts for writing style learning
    """
    __tablename__ = "user_posts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    x_account_id = Column(Integer, ForeignKey("x_accounts.id"), nullable=False)
    
    # Post content
    content = Column(Text, nullable=False)
    post_url = Column(String)
    
    # Engagement metrics
    likes = Column(Integer, default=0)
    retweets = Column(Integer, default=0)
    replies = Column(Integer, default=0)
    
    # Metadata
    posted_at = Column(DateTime)
    imported_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    x_account = relationship("XAccount", back_populates="posts")


class APIUsage(Base):
    """
    Track API usage for rate limiting and billing
    """
    __tablename__ = "api_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Usage tracking
    endpoint = Column(String, nullable=False)
    request_count = Column(Integer, default=1)

    # Timestamps
    date = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="api_usage")


class ScheduledPost(Base):
    """
    Scheduled posts for content calendar
    """
    __tablename__ = "scheduled_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    x_account_id = Column(Integer, ForeignKey("x_accounts.id"), nullable=False)

    # Post content
    content = Column(Text, nullable=False)
    media_urls = Column(JSON, default=[])  # Array of S3/Cloudinary URLs

    # Status
    status = Column(String, nullable=False, default="draft")  # draft, scheduled, posted, failed

    # Scheduling
    scheduled_at = Column(DateTime)  # When to post
    posted_at = Column(DateTime)  # When it was actually posted

    # AI metadata
    ai_generated = Column(Boolean, default=False)
    ai_confidence = Column(Integer)  # 0-100
    ai_metadata = Column(JSON, default={})  # Additional metadata (topics, rationale, etc.)

    # Error handling
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    x_account = relationship("XAccount")

