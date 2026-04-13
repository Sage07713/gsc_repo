package data

import (
	"time"

	"github.com/google/uuid"
)

type Alert struct {
	ID         uuid.UUID `db:"id"`
	DeviceID   uuid.UUID `db:"device_id"`
	ZoneID     uuid.UUID `db:"zone_id"`
	VenueID    uuid.UUID `db:"venue_id"`
	HazardType string    `db:"hazard_type"` // fire, medical, stampede
	Confidence float64   `db:"confidence"`
	ImageURL   string    `db:"image_url"` // stored in cloud
	Status     string    `db:"status"`    // detected, verified, resolved
	CreatedAt  time.Time `db:"created_at"`
}

type Notification struct {
	ID      uuid.UUID `db:"id"`
	AlertID uuid.UUID `db:"alert_id"`
	Target  string    `db:"target"`  // user/guest
	Channel string    `db:"channel"` // FCM, SMS
	Status  string    `db:"status"`  // sent, failed
	SentAt  time.Time `db:"sent_at"`
}

type Escalation struct {
	ID        uuid.UUID `db:"id"`
	AlertID   uuid.UUID `db:"alert_id"`
	Level     int       `db:"level"`     // 1=internal, 2=external
	Contacted string    `db:"contacted"` // "112", fire dept
	Response  string    `db:"response"`
	CreatedAt time.Time `db:"created_at"`
}
