CREATE TABLE IF NOT EXISTS guests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    venue_id UUID NOT NULL REFERENCES venues(id) ON DELETE CASCADE,

    room_no VARCHAR(20),
    device_id TEXT, -- FCM token / device identifier

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_guests_venue_id ON guests(venue_id);
