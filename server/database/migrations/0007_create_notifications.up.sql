CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    alert_id UUID NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,

    target_type VARCHAR(50), -- user / guest
    target_id UUID,

    channel VARCHAR(50), -- FCM / SMS
    status VARCHAR(50),  -- sent / failed

    sent_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_notifications_alert_id ON notifications(alert_id);
