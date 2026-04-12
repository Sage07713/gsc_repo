package data

import (
	"errors"
	"os"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

var (
	accessSecret  = []byte(os.Getenv("ACCESSTOKENSECRET"))
	refreshSecret = []byte(os.Getenv("REFRESHTOKENSECRET"))
)

const (
	accessExpiry  = 15 * time.Minute
	refreshExpiry = 7 * 24 * time.Hour
)

type Claims struct {
	UserId   string `json:"_id"`
	Username string `json:"username"`
	jwt.RegisteredClaims
}

func GenerateAccessToken(user *User) (string, error) {
	claims := Claims{
		UserId:   user.Id,
		Username: user.Username,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(accessExpiry)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
		},
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString([]byte(accessSecret))
}

func GenerateRefreshToken(user *User) (string, error) {
	claims := Claims{
		UserId:   user.Id,
		Username: user.Username,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(refreshExpiry)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
		},
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString([]byte(refreshSecret))
}

func ValidateToken(tokenStr string, secret []byte) (*Claims, error) {
	token, err := jwt.ParseWithClaims(tokenStr, &Claims{}, func(t *jwt.Token) (interface{}, error) {
		return secret, nil
	})
	if err != nil || !token.Valid {
		return nil, errors.New("invalid token")
	}

	claims, ok := token.Claims.(*Claims)
	if !ok {
		return nil, errors.New("could not parse claims")
	}
	return claims, nil
}

func ValidateAccessToken(tokenStr string) (*Claims, error) {
	return ValidateToken(tokenStr, accessSecret)
}

func ValidateRefreshToken(tokenStr string) (*Claims, error) {
	return ValidateToken(tokenStr, refreshSecret)
}
