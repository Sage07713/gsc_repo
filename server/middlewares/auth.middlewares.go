package middlewares

import (
	"context"
	"errors"
	"net/http"
	"os"
	"strings"

	"github.com/Shreyaskr1409/redpanda/data"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

func AuthMiddleware(db *pgxpool.Pool) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			tokenString := extractToken(r)
			if tokenString == "" {
				http.Error(w, "Unauthorised request", http.StatusUnauthorized)
				return
			}

			claims, err := data.ValidateToken(tokenString, []byte(os.Getenv("ACCESSTOKENSECRET")))
			if err != nil {
				http.Error(w, "Invalid Access Token", http.StatusUnauthorized)
				return
			}

			user, err := GetUserFromDB(r.Context(), db, claims.UserId)
			if err != nil {
				if errors.Is(err, pgx.ErrNoRows) {
					http.Error(w, "User not found", http.StatusUnauthorized)
					return
				}
				http.Error(w, "Database error", http.StatusInternalServerError)
				return
			}

			ctx := context.WithValue(r.Context(), "user", user)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func extractToken(r *http.Request) string {
	cookie, err := r.Cookie("accessToken")
	if err != nil && cookie.Value != "" {
		return cookie.Value
	}

	authHeader := r.Header.Get("Authorization")
	if authHeader != "" {
		parts := strings.Split(authHeader, " ")
		if len(parts) == 2 && parts[0] == "Bearer" {
			return parts[1]
		}
	}
	return ""
}

func GetUserFromDB(ctx context.Context, pool *pgxpool.Pool, userID string) (*data.User, error) {
	query := `
	SELECT _id, username, email
	FROM users
	WHERE id = $1
	`

	var user data.User
	err := pool.QueryRow(ctx, query, userID).Scan(
		&user.Id,
		&user.Username,
		&user.Email,
	)
	if err != nil {
		return nil, err
	}
	return &user, nil
}
