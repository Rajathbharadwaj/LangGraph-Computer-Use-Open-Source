-- Migration: Add Style Learning Tables for Continual Learning
-- Date: 2025-12-29
-- Description: Creates tables for style feedback tracking, evolution snapshots, and learned rules
-- Based on Letta's continual learning principles

-- ============================================================================
-- Table: style_feedback
-- Tracks user feedback on AI-generated content for continual learning
-- ============================================================================

CREATE TABLE IF NOT EXISTS style_feedback (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    x_account_id INTEGER REFERENCES x_accounts(id) ON DELETE SET NULL,

    -- Generation details
    generation_type VARCHAR(20) NOT NULL,  -- post, comment, thread
    generation_id VARCHAR(100),  -- External ID if applicable

    -- Content tracking
    original_content TEXT NOT NULL,  -- AI-generated content
    edited_content TEXT,  -- User's edited version (if modified)

    -- Feedback classification
    action VARCHAR(20) NOT NULL,  -- approved, edited, rejected, regenerated
    edit_distance FLOAT,  -- Levenshtein distance ratio (0-1)

    -- Explicit feedback
    rating INTEGER,  -- 1-5 stars or thumbs (1=down, 5=up)
    feedback_text TEXT,  -- Optional user comments
    feedback_tags JSONB DEFAULT '[]',  -- ["too_formal", "wrong_tone", "ai_sounding"]

    -- Analysis results (filled by FeedbackProcessor)
    removed_phrases JSONB DEFAULT '[]',  -- Phrases user removed
    added_phrases JSONB DEFAULT '[]',  -- Phrases user added
    learned_patterns JSONB DEFAULT '{}',  -- Extracted patterns

    -- Processing status
    processed BOOLEAN DEFAULT FALSE,  -- Has been processed by consolidation
    processed_at TIMESTAMP,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_style_feedback_user ON style_feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_style_feedback_action ON style_feedback(action);
CREATE INDEX IF NOT EXISTS idx_style_feedback_processed ON style_feedback(processed);
CREATE INDEX IF NOT EXISTS idx_style_feedback_created ON style_feedback(created_at DESC);

-- ============================================================================
-- Table: style_evolution_snapshots
-- Versioned snapshots of user's writing style for drift detection
-- ============================================================================

CREATE TABLE IF NOT EXISTS style_evolution_snapshots (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Snapshot identification
    snapshot_id VARCHAR(50) UNIQUE NOT NULL,  -- format: user_id_YYYYMMDD_HHmmss

    -- Style profile (full DeepStyleProfile as JSON)
    profile_json JSONB NOT NULL,

    -- Context at snapshot time
    post_count_at_snapshot INTEGER DEFAULT 0,
    comment_count_at_snapshot INTEGER DEFAULT 0,

    -- Trigger information
    trigger VARCHAR(50) DEFAULT 'manual',  -- manual, drift_detected, new_posts, scheduled

    -- Drift metrics (compared to previous snapshot)
    drift_from_previous FLOAT,
    drift_details JSONB DEFAULT '{}',

    -- Status
    is_active BOOLEAN DEFAULT TRUE,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_style_snapshots_user ON style_evolution_snapshots(user_id);
CREATE INDEX IF NOT EXISTS idx_style_snapshots_active ON style_evolution_snapshots(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_style_snapshots_created ON style_evolution_snapshots(created_at DESC);

-- ============================================================================
-- Table: learned_style_rules
-- Consolidated learned rules from user feedback
-- ============================================================================

CREATE TABLE IF NOT EXISTS learned_style_rules (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Rule details
    rule_type VARCHAR(30) NOT NULL,  -- banned_phrase, preferred_phrase, tone_adjustment, etc.
    rule_content TEXT NOT NULL,  -- The phrase or instruction

    -- Confidence and source
    confidence FLOAT DEFAULT 0.5,  -- 0-1, higher = more certain
    source_feedback_count INTEGER DEFAULT 1,
    source_feedback_ids JSONB DEFAULT '[]',

    -- Priority and status
    priority INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_applied_at TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_style_rules_user ON learned_style_rules(user_id);
CREATE INDEX IF NOT EXISTS idx_style_rules_type ON learned_style_rules(rule_type);
CREATE INDEX IF NOT EXISTS idx_style_rules_active ON learned_style_rules(user_id, is_active);

-- ============================================================================
-- Trigger: Auto-update updated_at on style_feedback
-- ============================================================================

CREATE OR REPLACE FUNCTION update_style_feedback_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS style_feedback_updated_at ON style_feedback;
CREATE TRIGGER style_feedback_updated_at
    BEFORE UPDATE ON style_feedback
    FOR EACH ROW
    EXECUTE FUNCTION update_style_feedback_updated_at();

-- ============================================================================
-- Trigger: Auto-update updated_at on learned_style_rules
-- ============================================================================

DROP TRIGGER IF EXISTS learned_style_rules_updated_at ON learned_style_rules;
CREATE TRIGGER learned_style_rules_updated_at
    BEFORE UPDATE ON learned_style_rules
    FOR EACH ROW
    EXECUTE FUNCTION update_style_feedback_updated_at();

-- ============================================================================
-- Comments for documentation
-- ============================================================================

COMMENT ON TABLE style_feedback IS 'Tracks user feedback on AI-generated content for continual learning';
COMMENT ON TABLE style_evolution_snapshots IS 'Versioned snapshots of user writing style for drift detection';
COMMENT ON TABLE learned_style_rules IS 'Consolidated learned rules from user feedback';

COMMENT ON COLUMN style_feedback.action IS 'User action on generated content: approved, edited, rejected, regenerated';
COMMENT ON COLUMN style_feedback.edit_distance IS 'Levenshtein distance ratio between original and edited content (0-1)';
COMMENT ON COLUMN style_feedback.processed IS 'Whether this feedback has been processed by the consolidation job';

COMMENT ON COLUMN style_evolution_snapshots.drift_from_previous IS 'Overall style drift score compared to previous snapshot (0-1)';
COMMENT ON COLUMN style_evolution_snapshots.is_active IS 'Whether this is the current active profile for the user';

COMMENT ON COLUMN learned_style_rules.confidence IS 'Rule confidence based on feedback count and consistency (0-1)';
COMMENT ON COLUMN learned_style_rules.priority IS 'Higher priority rules are applied first during generation';
