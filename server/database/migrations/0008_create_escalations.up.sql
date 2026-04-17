CREATE TABLE IF NOT EXISTS escalations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    alert_id UUID NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,

    level INT NOT NULL,
    contacted VARCHAR(100),
    response TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_escalations_alert_id ON escalations(alert_id);
