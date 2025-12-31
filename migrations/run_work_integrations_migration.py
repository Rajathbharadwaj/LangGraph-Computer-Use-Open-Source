#!/usr/bin/env python3
"""
Migration script to add Work Integrations tables.
Run via Cloud Run Jobs or locally with DB access.

Tables created:
- work_integrations: Connected work platforms (GitHub, Slack, etc.)
- work_integration_credentials: Encrypted OAuth tokens
- work_activities: Captured activities from platforms
- activity_drafts: AI-generated post drafts for review
"""
import os
import sys
from sqlalchemy import create_engine, text

def run_migration():
    database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URI")
    if not database_url:
        print("ERROR: DATABASE_URL or POSTGRES_URI not set")
        sys.exit(1)

    # Ensure sync driver for migration
    if "+asyncpg" in database_url:
        database_url = database_url.replace("+asyncpg", "")

    print(f"Connecting to database...")
    engine = create_engine(database_url)

    migrations = [
        # 1. Work Integrations table
        """
        CREATE TABLE IF NOT EXISTS work_integrations (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            platform VARCHAR(20) NOT NULL,
            external_account_id VARCHAR(100),
            external_account_name VARCHAR(255),
            github_repos JSONB DEFAULT '[]'::jsonb,
            github_org VARCHAR(100),
            slack_channels JSONB DEFAULT '[]'::jsonb,
            slack_workspace_id VARCHAR(50),
            notion_database_ids JSONB DEFAULT '[]'::jsonb,
            linear_team_id VARCHAR(50),
            figma_project_ids JSONB DEFAULT '[]'::jsonb,
            webhook_secret VARCHAR(64),
            webhook_registered BOOLEAN DEFAULT FALSE,
            webhook_url VARCHAR(500),
            is_connected BOOLEAN DEFAULT TRUE,
            is_active BOOLEAN DEFAULT TRUE,
            connection_error TEXT,
            scopes JSONB DEFAULT '[]'::jsonb,
            capture_commits BOOLEAN DEFAULT TRUE,
            capture_prs BOOLEAN DEFAULT TRUE,
            capture_releases BOOLEAN DEFAULT TRUE,
            capture_issues BOOLEAN DEFAULT TRUE,
            capture_comments BOOLEAN DEFAULT TRUE,
            credits_per_month INTEGER DEFAULT 100,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_synced_at TIMESTAMP,
            last_activity_at TIMESTAMP,
            UNIQUE(user_id, platform)
        );
        """,

        # 2. Work Integration Credentials table
        """
        CREATE TABLE IF NOT EXISTS work_integration_credentials (
            id SERIAL PRIMARY KEY,
            integration_id INTEGER NOT NULL REFERENCES work_integrations(id) ON DELETE CASCADE,
            encrypted_access_token TEXT,
            encrypted_refresh_token TEXT,
            token_expires_at TIMESTAMP,
            scopes JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(integration_id)
        );
        """,

        # 3. Activity Drafts table (create before work_activities for FK)
        """
        CREATE TABLE IF NOT EXISTS activity_drafts (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            x_account_id INTEGER NOT NULL REFERENCES x_accounts(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            ai_rationale TEXT,
            source_activity_ids JSONB DEFAULT '[]'::jsonb,
            activity_summary TEXT,
            digest_date DATE NOT NULL,
            digest_theme VARCHAR(100),
            status VARCHAR(20) DEFAULT 'pending',
            user_edited_content TEXT,
            scheduled_post_id INTEGER,
            scheduled_at TIMESTAMP,
            posted_at TIMESTAMP,
            expires_at TIMESTAMP,
            feedback_rating INTEGER,
            feedback_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP
        );
        """,

        # 4. Work Activities table
        """
        CREATE TABLE IF NOT EXISTS work_activities (
            id SERIAL PRIMARY KEY,
            integration_id INTEGER NOT NULL REFERENCES work_integrations(id) ON DELETE CASCADE,
            user_id VARCHAR(255) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            platform VARCHAR(20) NOT NULL,
            external_id VARCHAR(100),
            activity_type VARCHAR(50) NOT NULL,
            category VARCHAR(30) DEFAULT 'progress',
            title VARCHAR(500) NOT NULL,
            description TEXT,
            url VARCHAR(500),
            repo_or_project VARCHAR(200),
            lines_added INTEGER DEFAULT 0,
            lines_removed INTEGER DEFAULT 0,
            files_changed INTEGER DEFAULT 0,
            comments_count INTEGER DEFAULT 0,
            reactions_count INTEGER DEFAULT 0,
            significance_score FLOAT DEFAULT 0.0,
            raw_payload JSONB DEFAULT '{}'::jsonb,
            processed BOOLEAN DEFAULT FALSE,
            processed_at TIMESTAMP,
            draft_id INTEGER REFERENCES activity_drafts(id) ON DELETE SET NULL,
            activity_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(integration_id, external_id)
        );
        """,

        # 5. Add scheduled_posts FK to activity_drafts (if scheduled_posts exists)
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'scheduled_posts') THEN
                ALTER TABLE activity_drafts
                ADD CONSTRAINT fk_activity_drafts_scheduled_post
                FOREIGN KEY (scheduled_post_id) REFERENCES scheduled_posts(id) ON DELETE SET NULL;
            END IF;
        EXCEPTION WHEN duplicate_object THEN
            NULL;
        END $$;
        """,

        # 6. Indexes
        """
        CREATE INDEX IF NOT EXISTS idx_work_integrations_user_id ON work_integrations(user_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_work_integrations_platform ON work_integrations(platform);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_work_integrations_active ON work_integrations(is_connected, is_active);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_work_activities_user_id ON work_activities(user_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_work_activities_integration_id ON work_activities(integration_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_work_activities_activity_at ON work_activities(activity_at);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_work_activities_processed ON work_activities(processed);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_work_activities_platform ON work_activities(platform);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_activity_drafts_user_id ON activity_drafts(user_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_activity_drafts_status ON activity_drafts(status);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_activity_drafts_digest_date ON activity_drafts(digest_date);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_activity_drafts_expires_at ON activity_drafts(expires_at);
        """,

        # 7. Add name column to users if not exists
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(255);
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
                # These are OK - means already exists
                if "already exists" in error_msg or "duplicate" in error_msg.lower():
                    print(f"  ✓ Migration {i} skipped (already exists)")
                    conn.rollback()
                else:
                    print(f"  ✗ Migration {i} error: {e}")
                    conn.rollback()

    print("\n✅ Work Integrations migration complete!")
    print("\nTables created:")
    print("  - work_integrations")
    print("  - work_integration_credentials")
    print("  - work_activities")
    print("  - activity_drafts")

if __name__ == "__main__":
    run_migration()
