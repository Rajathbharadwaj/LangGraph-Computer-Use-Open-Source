-- Work Integrations Migration
-- Creates tables for work platform integrations (GitHub, Slack, Notion, Linear, Figma)
-- Run via: psql $DATABASE_URL -f migrations/add_work_integrations_tables.sql

-- 1. Work Integrations table (main integration config)
CREATE TABLE IF NOT EXISTS work_integrations (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Platform identification
    platform VARCHAR(20) NOT NULL,  -- github, slack, notion, linear, figma
    external_account_id VARCHAR(100),
    external_account_name VARCHAR(255),

    -- Platform-specific configuration (JSON)
    github_repos JSONB DEFAULT '[]'::jsonb,
    github_org VARCHAR(100),
    slack_channels JSONB DEFAULT '[]'::jsonb,
    slack_workspace_id VARCHAR(50),
    notion_database_ids JSONB DEFAULT '[]'::jsonb,
    linear_team_id VARCHAR(50),
    figma_project_ids JSONB DEFAULT '[]'::jsonb,

    -- Webhook configuration
    webhook_secret VARCHAR(64),
    webhook_registered BOOLEAN DEFAULT FALSE,
    webhook_url VARCHAR(500),

    -- Status
    is_connected BOOLEAN DEFAULT TRUE,
    is_active BOOLEAN DEFAULT TRUE,
    connection_error TEXT,
    scopes JSONB DEFAULT '[]'::jsonb,

    -- Activity capture settings
    capture_commits BOOLEAN DEFAULT TRUE,
    capture_prs BOOLEAN DEFAULT TRUE,
    capture_releases BOOLEAN DEFAULT TRUE,
    capture_issues BOOLEAN DEFAULT TRUE,
    capture_comments BOOLEAN DEFAULT TRUE,

    -- Billing
    credits_per_month INTEGER DEFAULT 100,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_synced_at TIMESTAMP,
    last_activity_at TIMESTAMP,

    -- Unique constraint: one integration per platform per user
    UNIQUE(user_id, platform)
);

-- 2. Work Integration Credentials table (encrypted OAuth tokens)
CREATE TABLE IF NOT EXISTS work_integration_credentials (
    id SERIAL PRIMARY KEY,
    integration_id INTEGER NOT NULL REFERENCES work_integrations(id) ON DELETE CASCADE,

    -- Encrypted tokens
    encrypted_access_token TEXT,
    encrypted_refresh_token TEXT,

    -- Token metadata
    token_expires_at TIMESTAMP,
    scopes JSONB,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(integration_id)
);

-- 3. Work Activities table (normalized activity records)
CREATE TABLE IF NOT EXISTS work_activities (
    id SERIAL PRIMARY KEY,
    integration_id INTEGER NOT NULL REFERENCES work_integrations(id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Activity identification
    platform VARCHAR(20) NOT NULL,
    external_id VARCHAR(100),
    activity_type VARCHAR(50) NOT NULL,
    category VARCHAR(30) DEFAULT 'progress',

    -- Content
    title VARCHAR(500) NOT NULL,
    description TEXT,
    url VARCHAR(500),
    repo_or_project VARCHAR(200),

    -- Metrics for scoring
    lines_added INTEGER DEFAULT 0,
    lines_removed INTEGER DEFAULT 0,
    files_changed INTEGER DEFAULT 0,
    comments_count INTEGER DEFAULT 0,
    reactions_count INTEGER DEFAULT 0,

    -- Significance scoring
    significance_score FLOAT DEFAULT 0.0,

    -- Raw payload for debugging
    raw_payload JSONB DEFAULT '{}'::jsonb,

    -- Processing status
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP,
    draft_id INTEGER,  -- FK added after activity_drafts table exists

    -- Timestamps
    activity_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Prevent duplicate activities
    UNIQUE(integration_id, external_id)
);

-- 4. Activity Drafts table (AI-generated post drafts)
CREATE TABLE IF NOT EXISTS activity_drafts (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    x_account_id INTEGER NOT NULL REFERENCES x_accounts(id) ON DELETE CASCADE,

    -- Generated content
    content TEXT NOT NULL,
    ai_rationale TEXT,

    -- Source activities
    source_activity_ids JSONB DEFAULT '[]'::jsonb,
    activity_summary TEXT,

    -- Digest metadata
    digest_date DATE NOT NULL,
    digest_theme VARCHAR(100),

    -- Status
    status VARCHAR(20) DEFAULT 'pending',  -- pending, approved, edited, rejected, expired, scheduled, posted
    user_edited_content TEXT,

    -- Scheduling
    scheduled_post_id INTEGER REFERENCES scheduled_posts(id),
    scheduled_at TIMESTAMP,
    posted_at TIMESTAMP,

    -- Expiration
    expires_at TIMESTAMP,

    -- User feedback
    feedback_rating INTEGER,
    feedback_text TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP
);

-- Add FK from work_activities.draft_id to activity_drafts.id
ALTER TABLE work_activities
ADD CONSTRAINT fk_work_activities_draft
FOREIGN KEY (draft_id) REFERENCES activity_drafts(id) ON DELETE SET NULL;

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_work_integrations_user_id ON work_integrations(user_id);
CREATE INDEX IF NOT EXISTS idx_work_integrations_platform ON work_integrations(platform);
CREATE INDEX IF NOT EXISTS idx_work_integrations_active ON work_integrations(is_connected, is_active);

CREATE INDEX IF NOT EXISTS idx_work_activities_user_id ON work_activities(user_id);
CREATE INDEX IF NOT EXISTS idx_work_activities_integration_id ON work_activities(integration_id);
CREATE INDEX IF NOT EXISTS idx_work_activities_activity_at ON work_activities(activity_at);
CREATE INDEX IF NOT EXISTS idx_work_activities_processed ON work_activities(processed);
CREATE INDEX IF NOT EXISTS idx_work_activities_platform ON work_activities(platform);

CREATE INDEX IF NOT EXISTS idx_activity_drafts_user_id ON activity_drafts(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_drafts_status ON activity_drafts(status);
CREATE INDEX IF NOT EXISTS idx_activity_drafts_digest_date ON activity_drafts(digest_date);
CREATE INDEX IF NOT EXISTS idx_activity_drafts_expires_at ON activity_drafts(expires_at);

-- Add name column to users table if not exists (needed for email notifications)
ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(255);
