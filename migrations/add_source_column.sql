-- Migration: Add source column to user_posts and user_comments tables
-- Run this against your Cloud SQL database

-- Add source column to user_posts if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_posts' AND column_name = 'source'
    ) THEN
        ALTER TABLE user_posts ADD COLUMN source VARCHAR(20) DEFAULT 'imported';
    END IF;
END $$;

-- Add source column to user_comments if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_comments' AND column_name = 'source'
    ) THEN
        ALTER TABLE user_comments ADD COLUMN source VARCHAR(20) DEFAULT 'imported';
    END IF;
END $$;

-- Add retweets column to user_comments if it doesn't exist (for parity with posts)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_comments' AND column_name = 'retweets'
    ) THEN
        ALTER TABLE user_comments ADD COLUMN retweets INTEGER DEFAULT 0;
    END IF;
END $$;

-- Verify the columns were added
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name IN ('user_posts', 'user_comments')
AND column_name IN ('source', 'retweets')
ORDER BY table_name, column_name;
