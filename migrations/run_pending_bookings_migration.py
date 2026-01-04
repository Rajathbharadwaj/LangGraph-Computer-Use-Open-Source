#!/usr/bin/env python3
"""
Migration script to add Pending Bookings table for Voice Agent POC.
Run via Cloud Run Jobs or locally with DB access.

Tables created:
- pending_bookings: Booking form submissions from voice agent calls
"""
import os
import sys
from sqlalchemy import create_engine, text


def run_migration():
    database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URI")

    # Support building URL from components (for Cloud Run Jobs)
    if not database_url:
        db_password = os.environ.get("DB_PASSWORD")
        db_host = os.environ.get("POSTGRES_HOST", "10.97.0.3")
        db_user = os.environ.get("POSTGRES_USER", "postgres")
        db_name = os.environ.get("POSTGRES_DB", "parallel_universe_db")

        if db_password:
            from urllib.parse import quote
            encoded_password = quote(db_password, safe='')
            database_url = f"postgresql://{db_user}:{encoded_password}@{db_host}:5432/{db_name}"
            print(f"Built DATABASE_URL from components (host: {db_host})")
        else:
            print("ERROR: DATABASE_URL/POSTGRES_URI not set and DB_PASSWORD not available")
            sys.exit(1)

    # Ensure sync driver for migration
    if "+asyncpg" in database_url:
        database_url = database_url.replace("+asyncpg", "")

    print(f"Connecting to database...")
    engine = create_engine(database_url)

    migrations = [
        # 1. Pending Bookings table
        """
        CREATE TABLE IF NOT EXISTS pending_bookings (
            id VARCHAR(12) PRIMARY KEY,
            call_session_id VARCHAR(100),
            webhook_url VARCHAR(500),
            phone_number VARCHAR(20) NOT NULL,
            proposed_datetime TIMESTAMP,
            contact_name VARCHAR(255),
            contact_email VARCHAR(255),
            company_name VARCHAR(255),
            selected_datetime TIMESTAMP,
            status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            submitted_at TIMESTAMP,
            expires_at TIMESTAMP
        );
        """,

        # 2. Indexes
        """
        CREATE INDEX IF NOT EXISTS idx_pending_bookings_call_session ON pending_bookings(call_session_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_pending_bookings_phone ON pending_bookings(phone_number);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_pending_bookings_status ON pending_bookings(status);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_pending_bookings_expires_at ON pending_bookings(expires_at);
        """,
    ]

    with engine.connect() as conn:
        for i, migration in enumerate(migrations, 1):
            try:
                print(f"Running migration {i}/{len(migrations)}...")
                conn.execute(text(migration))
                conn.commit()
                print(f"  ✓ Migration {i} complete")
            except Exception as e:
                error_msg = str(e)
                if "already exists" in error_msg or "duplicate" in error_msg.lower():
                    print(f"  ✓ Migration {i} skipped (already exists)")
                    conn.rollback()
                else:
                    print(f"  ✗ Migration {i} error: {e}")
                    conn.rollback()

    print("\n✅ Pending Bookings migration complete!")
    print("\nTable created:")
    print("  - pending_bookings")


if __name__ == "__main__":
    run_migration()
