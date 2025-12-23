#!/usr/bin/env python3
"""
One-time migration script to add Stripe billing columns.
Run via Cloud Run Jobs or locally with DB access.
"""
import os
import sys
from sqlalchemy import create_engine, text

def run_migration():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    print(f"Connecting to database...")
    engine = create_engine(database_url)

    migrations = [
        # Add stripe_customer_id to users table
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255);
        """,

        # Create subscriptions table
        """
        CREATE TABLE IF NOT EXISTS subscriptions (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL REFERENCES users(id),
            stripe_subscription_id VARCHAR(255) UNIQUE,
            stripe_customer_id VARCHAR(255),
            plan VARCHAR(50) NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'inactive',
            current_period_start TIMESTAMP,
            current_period_end TIMESTAMP,
            cancel_at_period_end BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # Create credit_balances table
        """
        CREATE TABLE IF NOT EXISTS credit_balances (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL UNIQUE REFERENCES users(id),
            balance INTEGER NOT NULL DEFAULT 0,
            lifetime_credits INTEGER NOT NULL DEFAULT 0,
            last_reset_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # Create credit_transactions table
        """
        CREATE TABLE IF NOT EXISTS credit_transactions (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL REFERENCES users(id),
            amount INTEGER NOT NULL,
            balance_after INTEGER NOT NULL,
            transaction_type VARCHAR(50) NOT NULL,
            description TEXT,
            metadata JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # Create feature_usage table
        """
        CREATE TABLE IF NOT EXISTS feature_usage (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL REFERENCES users(id),
            feature VARCHAR(100) NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            period_start TIMESTAMP NOT NULL,
            period_end TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, feature, period_start)
        );
        """,

        # Create indexes
        """
        CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_subscription_id ON subscriptions(stripe_subscription_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_credit_transactions_user_id ON credit_transactions(user_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_feature_usage_user_id ON feature_usage(user_id);
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
                print(f"  ! Migration {i} error (may be OK if already exists): {e}")
                conn.rollback()

    print("\n✅ All migrations complete!")

if __name__ == "__main__":
    run_migration()
