CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    zone_id UUID NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    venue_id UUID NOT NULL REFERENCES venues(id) ON DELETE CASCADE,

    hazard_type VARCHAR(50) NOT NULL,
    confidence DOUBLE PRECISION,

    image_url TEXT,

    status VARCHAR(50) NOT NULL DEFAULT 'detected',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_device_id ON alerts(device_id);
CREATE INDEX IF NOT EXISTS idx_alerts_zone_id ON alerts(zone_id);
CREATE INDEX IF NOT EXISTS idx_alerts_venue_id ON alerts(venue_id);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
