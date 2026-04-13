-- Add venue relation
ALTER TABLE users
ADD COLUMN IF NOT EXISTS venue_id UUID REFERENCES venues(id) ON DELETE CASCADE;

-- Add role system
ALTER TABLE users
ADD COLUMN IF NOT EXISTS role VARCHAR(50) NOT NULL DEFAULT 'staff';

-- Optional: index for queries
CREATE INDEX IF NOT EXISTS idx_users_venue_id ON users(venue_id);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
