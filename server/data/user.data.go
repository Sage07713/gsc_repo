package data

import "time"

// "github.com/go-playground/validator/v10"

type User struct {
	Id           string `json:"_id"`
	Username     string `json:"username"`
	Fullname     string `json:"fullname"`
	Email        string `json:"email"`
	Password     string `json:"password"`
	RefreshToken string `json:"refresh_token"`

	VenueID string `json:"venue_id"`
	Role    string `json:"role"` // (admin, staff, security)

	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}
