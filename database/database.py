"""
Database connection and session management
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Get database URL from environment (port 5433 to avoid conflict with other postgres instances)
# Check both POSTGRES_URI (LangGraph) and DATABASE_URL (backend-api)
DATABASE_URL = os.getenv("POSTGRES_URI") or os.getenv("DATABASE_URL") or "postgresql://postgres:password@localhost:5433/xgrowth"

# Create sync engine with connection timeout for Cloud Run startup
engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,  # For async compatibility
    echo=False,  # Set to True for SQL logging
    connect_args={
        "connect_timeout": 10,  # 10 second connection timeout
    },
)

# Create sync session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

# --- Async Database Support ---
# Convert sync URL to async URL for asyncpg driver
ASYNC_DATABASE_URL = DATABASE_URL
if "postgresql://" in ASYNC_DATABASE_URL and "+asyncpg" not in ASYNC_DATABASE_URL:
    ASYNC_DATABASE_URL = ASYNC_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

# Create async engine
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session():
    """
    Async dependency for FastAPI to get database session.
    Used by work_integrations and other async routes.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


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
    # Import billing models to ensure they're created
    from .models import Subscription, CreditBalance, CreditTransaction, FeatureUsage
    # Import comment tracking models
    from .models import UserComment, ReceivedComment
    # Import Learning Engine models (recommendation + preference learning)
    from .models import PostRecommendation, PreferenceSignal, RecommendationModel
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created")

    # Run migrations for columns that create_all won't add to existing tables
    run_migrations()


def run_migrations():
    """
    Run manual migrations for columns that create_all doesn't handle
    """
    from sqlalchemy import text

    migrations = [
        # Add stripe_customer_id to users table if it doesn't exist
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'stripe_customer_id'
            ) THEN
                ALTER TABLE users ADD COLUMN stripe_customer_id VARCHAR(255);
            END IF;
        END $$;
        """,
    ]

    with engine.connect() as conn:
        for migration in migrations:
            try:
                conn.execute(text(migration))
                conn.commit()
            except Exception as e:
                print(f"Migration warning: {e}")
                conn.rollback()

    print("✅ Database migrations complete")

