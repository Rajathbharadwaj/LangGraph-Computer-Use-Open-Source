"""
Database connection and session management
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

# Get database URL from environment (port 5433 to avoid conflict with other postgres instances)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5433/xgrowth")

# Create engine with connection timeout for Cloud Run startup
engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,  # For async compatibility
    echo=False,  # Set to True for SQL logging
    connect_args={
        "connect_timeout": 10,  # 10 second connection timeout
    },
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

def get_db():
    """
    Dependency for FastAPI to get database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """
    Initialize database tables
    """
    from .models import User, XAccount, UserCookies, UserPost, APIUsage, ScheduledPost
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created")

