"""
Run database migrations to add new columns.
Execute from the cua directory: python migrations/run_migration.py
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.database import SessionLocal, engine
from sqlalchemy import text


def run_migration():
    """Add source column to user_posts and user_comments tables."""

    migrations = [
        # Add source column to user_posts
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'user_posts' AND column_name = 'source'
            ) THEN
                ALTER TABLE user_posts ADD COLUMN source VARCHAR(20) DEFAULT 'imported';
                RAISE NOTICE 'Added source column to user_posts';
            ELSE
                RAISE NOTICE 'source column already exists in user_posts';
            END IF;
        END $$;
        """,

        # Add source column to user_comments
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'user_comments' AND column_name = 'source'
            ) THEN
                ALTER TABLE user_comments ADD COLUMN source VARCHAR(20) DEFAULT 'imported';
                RAISE NOTICE 'Added source column to user_comments';
            ELSE
                RAISE NOTICE 'source column already exists in user_comments';
            END IF;
        END $$;
        """,

        # Add retweets column to user_comments
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'user_comments' AND column_name = 'retweets'
            ) THEN
                ALTER TABLE user_comments ADD COLUMN retweets INTEGER DEFAULT 0;
                RAISE NOTICE 'Added retweets column to user_comments';
            ELSE
                RAISE NOTICE 'retweets column already exists in user_comments';
            END IF;
        END $$;
        """,
    ]

    with engine.connect() as conn:
        for migration in migrations:
            try:
                conn.execute(text(migration))
                conn.commit()
                print("Migration executed successfully")
            except Exception as e:
                print(f"Migration error: {e}")
                conn.rollback()

        # Verify columns
        result = conn.execute(text("""
            SELECT table_name, column_name, data_type, column_default
            FROM information_schema.columns
            WHERE table_name IN ('user_posts', 'user_comments')
            AND column_name IN ('source', 'retweets')
            ORDER BY table_name, column_name;
        """))

        print("\nCurrent columns:")
        for row in result:
            print(f"  {row[0]}.{row[1]}: {row[2]} (default: {row[3]})")


if __name__ == "__main__":
    print("Running database migration...")
    run_migration()
    print("\nMigration complete!")
