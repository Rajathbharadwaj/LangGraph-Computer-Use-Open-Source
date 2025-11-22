#!/usr/bin/env python3
"""
Database initialization script for Cloud SQL
Creates all tables based on SQLAlchemy models
"""
import os
import sys
from database import init_db, SessionLocal
from database.models import User, XAccount, UserCookies, UserPost, APIUsage, ScheduledPost

def main():
    """Initialize database tables"""
    try:
        print("Initializing database...")
        print(f"Database URL: {os.getenv('DATABASE_URL', 'Not set')}")

        # Create all tables
        init_db()

        print("✅ Database tables created successfully!")
        print("\nTables created:")
        print("  - users")
        print("  - x_accounts")
        print("  - user_cookies")
        print("  - user_posts")
        print("  - api_usage")
        print("  - scheduled_posts")

        # Test connection
        db = SessionLocal()
        result = db.execute("SELECT version();")
        version = result.fetchone()[0]
        print(f"\n✅ PostgreSQL version: {version}")
        db.close()

        return 0

    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
