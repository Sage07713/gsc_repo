package data

import (
	"time"

	"github.com/google/uuid"
)

type Guest struct {
	ID        uuid.UUID `db:"id"`
	VenueID   uuid.UUID `db:"venue_id"`
	RoomNo    string    `db:"room_no"`
	DeviceID  string    `db:"device_id"` // for push notifications
	CreatedAt time.Time `db:"created_at"`
}
