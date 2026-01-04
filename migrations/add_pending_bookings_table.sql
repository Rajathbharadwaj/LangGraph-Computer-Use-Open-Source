-- Voice Agent POC: Pending Bookings Migration
-- Creates table for booking form submissions during/after sales calls
-- Run via: psql $DATABASE_URL -f migrations/add_pending_bookings_table.sql

-- Pending Bookings table (Voice Agent POC)
-- No user_id FK - this is for prospects who haven't signed up yet
CREATE TABLE IF NOT EXISTS pending_bookings (
    id VARCHAR(12) PRIMARY KEY,  -- Short URL-safe ID: abc123de
    call_session_id VARCHAR(100),  -- Twilio Call SID for webhook routing
    webhook_url VARCHAR(500),  -- Voice agent callback URL
    phone_number VARCHAR(20) NOT NULL,  -- Prospect's phone (E.164 format)

    -- Proposed meeting time (from voice call)
    proposed_datetime TIMESTAMP,

    -- Prospect details (filled via form)
    contact_name VARCHAR(255),
    contact_email VARCHAR(255),
    company_name VARCHAR(255),

    -- Selected meeting time (may differ from proposed)
    selected_datetime TIMESTAMP,

    -- Status tracking
    status VARCHAR(20) DEFAULT 'pending',  -- pending, submitted, expired

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    submitted_at TIMESTAMP,
    expires_at TIMESTAMP  -- created_at + 1 hour
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_pending_bookings_call_session ON pending_bookings(call_session_id);
CREATE INDEX IF NOT EXISTS idx_pending_bookings_phone ON pending_bookings(phone_number);
CREATE INDEX IF NOT EXISTS idx_pending_bookings_status ON pending_bookings(status);
CREATE INDEX IF NOT EXISTS idx_pending_bookings_expires_at ON pending_bookings(expires_at);
