package data

import (
	"time"

	"github.com/google/uuid"
)

type Venue struct {
	ID        uuid.UUID `db:"id"`
	Name      string    `db:"name"`
	Address   string    `db:"address"`
	City      string    `db:"city"`
	CreatedAt time.Time `db:"created_at"`
}

type Zone struct {
	ID      uuid.UUID `db:"id"`
	VenueID uuid.UUID `db:"venue_id"`
	Name    string    `db:"name"` // "Floor 3 - Corridor B"
	Floor   int       `db:"floor"`
	MapRef  string    `db:"map_ref"` // optional layout reference
}

type Device struct {
	ID        uuid.UUID `db:"id"`
	VenueID   uuid.UUID `db:"venue_id"`
	ZoneID    uuid.UUID `db:"zone_id"`
	Name      string    `db:"name"`
	Type      string    `db:"type"` // "camera", "smoke_sensor"
	IPAddress string    `db:"ip_address"`
	Status    string    `db:"status"` // active/offline
	LastSeen  time.Time `db:"last_seen"`
}
