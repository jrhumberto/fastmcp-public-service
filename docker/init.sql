-- Sample schema for local development
-- Replace with your actual schema in production

CREATE TABLE IF NOT EXISTS records (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    description TEXT,
    status      TEXT NOT NULL DEFAULT 'active',
    type        TEXT,
    category    TEXT,
    metadata    JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_records_status   ON records(status);
CREATE INDEX idx_records_name     ON records USING gin(to_tsvector('english', name));
CREATE INDEX idx_records_created  ON records(created_at DESC);

-- Sample data
INSERT INTO records (name, description, status, type, category)
VALUES
    ('Sample Record A', 'First sample record for testing', 'active', 'typeA', 'cat1'),
    ('Sample Record B', 'Second sample record for testing', 'inactive', 'typeB', 'cat2'),
    ('Sample Record C', 'Third sample record for testing', 'active', 'typeA', 'cat1');
