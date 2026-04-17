CREATE TABLE IF NOT EXISTS devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    venue_id UUID NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    zone_id UUID NOT NULL REFERENCES zones(id) ON DELETE CASCADE,

    name VARCHAR(255),
    type VARCHAR(50) NOT NULL,
    ip_address VARCHAR(100),

    status VARCHAR(50) DEFAULT 'active',
    last_seen TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_devices_zone_id ON devices(zone_id);
CREATE INDEX IF NOT EXISTS idx_devices_status ON devices(status);
