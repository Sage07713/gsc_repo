package handlers

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/Shreyaskr1409/redpanda/data"
	"github.com/Shreyaskr1409/redpanda/utils"
	"github.com/gorilla/mux"
	"github.com/jackc/pgx/v5/pgxpool"
	"golang.org/x/crypto/bcrypt"
)

type UserHandler struct {
	l  *log.Logger
	db *pgxpool.Pool
}

func NewUserHandler(l *log.Logger, db *pgxpool.Pool) *UserHandler {
	return &UserHandler{
		l:  l,
		db: db,
	}
}

func (h *UserHandler) Register(w http.ResponseWriter, r *http.Request) {
	var userReq data.User
	if err := utils.ParseRequest(r, &userReq); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	if strings.TrimSpace(userReq.Username) == "" ||
		strings.TrimSpace(userReq.Email) == "" ||
		strings.TrimSpace(userReq.Email) == "" ||
		strings.TrimSpace(userReq.Fullname) == "" {
		http.Error(w, "All fields are required", http.StatusBadRequest)
		return
	}

	var exists bool
	ctx := context.Background()
	defer ctx.Done()
	err := h.db.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM users WHERE username = $1 OR email = $2)", userReq.Username, userReq.Email).Scan(&exists)
	if err != nil {
		h.l.Println("Database error while uploading the data: ", err)
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}
	if exists {
		h.l.Println("User with the given credentials already exists")
		http.Error(w, "User with the given credentials already exists", http.StatusConflict)
		return
	}

	hashedPassword, err := bcrypt.GenerateFromPassword([]byte(userReq.Password), bcrypt.DefaultCost)
	if err != nil {
		h.l.Println("Unable to hash the password: ", err)
		http.Error(w, "Failed to hash password", http.StatusInternalServerError)
		return
	}
	now := time.Now()
	refreshToken, err := data.GenerateRefreshToken(&userReq)
	if err != nil {
		h.l.Println("Failed to generate refresh token: ", err)
		http.Error(w, "Failed to generate refresh token", http.StatusInternalServerError)
		return
	}

	_, err = h.db.Exec(ctx,
		`INSERT INTO users
		(username, fullname, email, password, refresh_token, created_at, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7)`,
		userReq.Username,
		userReq.Fullname,
		userReq.Email,
		hashedPassword,
		refreshToken,
		now,
		now,
	)
	if err != nil {
		h.l.Println("Database error creating user: ", err)
		http.Error(w, "Failed to create user", http.StatusInternalServerError)
		return
	}

	var id string
	err = h.db.QueryRow(ctx,
		`SELECT id
        FROM users WHERE username = $1 OR email = $1`,
		&userReq.Username,
	).Scan(
		id,
	)
	if err != nil {
		h.l.Println("Database error while fetching user: ", err)
		http.Error(w, "Invalid credentials", http.StatusUnauthorized)
		return
	}

	newUser := data.User{
		Id:           id,
		Username:     userReq.Username,
		Fullname:     userReq.Fullname,
		Email:        userReq.Email,
		RefreshToken: refreshToken,
		CreatedAt:    now,
		UpdatedAt:    now,
	}

	w.Header().Set("Content-Type", "application/json")
	if err = json.NewEncoder(w).Encode(newUser); err != nil {
		h.l.Println("Error encoding response:", err)
		http.Error(w, "Internal Server Error (But the user is created successfully)", http.StatusInternalServerError)
		return
	}
}

func (h *UserHandler) Login(w http.ResponseWriter, r *http.Request) {
	var loginReq struct {
		Username string `json:"username"`
		Password string `json:"password"`
	}

	if err := utils.ParseRequest(r, &loginReq); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	if strings.TrimSpace(loginReq.Username) == "" || strings.TrimSpace(loginReq.Password) == "" {
		http.Error(w, "Username and password are required", http.StatusBadRequest)
		return
	}

	var user data.User
	ctx := context.Background()
	err := h.db.QueryRow(ctx,
		`SELECT id, username, fullname, email, password, refresh_token, created_at, updated_at
        FROM users WHERE username = $1 OR email = $1`,
		loginReq.Username,
	).Scan(
		&user.Id,
		&user.Username,
		&user.Fullname,
		&user.Email,
		&user.Password,
		&user.RefreshToken,
		&user.CreatedAt,
		&user.UpdatedAt,
	)
	if err != nil {
		h.l.Println("Database error while fetching user: ", err)
		http.Error(w, "Invalid credentials", http.StatusUnauthorized)
		return
	}

	if err := bcrypt.CompareHashAndPassword([]byte(user.Password), []byte(loginReq.Password)); err != nil {
		h.l.Println("Invalid password: ", err)
		http.Error(w, "Invalid credentials", http.StatusUnauthorized)
		return
	}

	accessToken, err := data.GenerateAccessToken(&user)
	if err != nil {
		h.l.Println("Failed to generate access token: ", err)
		http.Error(w, "Failed to generate token", http.StatusInternalServerError)
		return
	}

	refreshToken, err := data.GenerateRefreshToken(&user)
	if err != nil {
		h.l.Println("Failed to generate refresh token: ", err)
		http.Error(w, "Failed to generate token", http.StatusInternalServerError)
		return
	}

	// Update refresh token in database
	_, err = h.db.Exec(ctx,
		"UPDATE users SET refresh_token = $1, updated_at = $2 WHERE id = $3",
		refreshToken,
		time.Now(),
		user.Id,
	)
	if err != nil {
		h.l.Println("Failed to update refresh token: ", err)
		http.Error(w, "Failed to update token", http.StatusInternalServerError)
		return
	}

	response := map[string]interface{}{
		"user":          user,
		"access_token":  accessToken,
		"refresh_token": refreshToken,
	}

	w.Header().Set("Content-Type", "application/json")
	if err = json.NewEncoder(w).Encode(response); err != nil {
		h.l.Println("Error encoding response:", err)
		http.Error(w, "Internal Server Error", http.StatusInternalServerError)
	}
}

func (h *UserHandler) Logout(w http.ResponseWriter, r *http.Request) {
	authHeader := r.Header.Get("Authorization")
	if authHeader == "" {
		http.Error(w, "Authorization header required", http.StatusUnauthorized)
		return
	}

	tokenStr := strings.TrimPrefix(authHeader, "Bearer ")
	claims, err := data.ValidateAccessToken(tokenStr)
	if err != nil {
		h.l.Println("Invalid token: ", err)
		http.Error(w, "Invalid token", http.StatusUnauthorized)
		return
	}

	ctx := context.Background()
	_, err = h.db.Exec(ctx,
		"UPDATE users SET refresh_token = NULL, updated_at = $1 WHERE id = $2",
		time.Now(),
		claims.UserId,
	)
	if err != nil {
		h.l.Println("Database error during logout: ", err)
		http.Error(w, "Failed to logout", http.StatusInternalServerError)
		return
	}

	// Clear cookies
	http.SetCookie(w, &http.Cookie{
		Name:     "accessToken",
		Value:    "",
		Path:     "/",
		HttpOnly: true,
		Secure:   true,
		MaxAge:   -1,
	})
	http.SetCookie(w, &http.Cookie{
		Name:     "refreshToken",
		Value:    "",
		Path:     "/",
		HttpOnly: true,
		Secure:   true,
		MaxAge:   -1,
	})

	w.WriteHeader(http.StatusNoContent)
}

func (h *UserHandler) GetUser(w http.ResponseWriter, r *http.Request) {
	authHeader := r.Header.Get("Authorization")
	if authHeader == "" {
		http.Error(w, "Authorization header required", http.StatusUnauthorized)
		return
	}

	tokenStr := strings.TrimPrefix(authHeader, "Bearer ")
	claims, err := data.ValidateAccessToken(tokenStr)
	if err != nil {
		h.l.Println("Invalid token: ", err)
		http.Error(w, "Invalid token", http.StatusUnauthorized)
		return
	}

	var user data.User
	ctx := context.Background()
	err = h.db.QueryRow(ctx,
		`SELECT id, username, fullname, email, created_at, updated_at
        FROM users WHERE id = $1`,
		claims.UserId,
	).Scan(
		&user.Id,
		&user.Username,
		&user.Fullname,
		&user.Email,
		&user.CreatedAt,
		&user.UpdatedAt,
	)
	if err != nil {
		h.l.Println("Database error while fetching user: ", err)
		http.Error(w, "User not found", http.StatusNotFound)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	if err = json.NewEncoder(w).Encode(user); err != nil {
		h.l.Println("Error encoding response:", err)
		http.Error(w, "Internal Server Error", http.StatusInternalServerError)
	}
}

func (h *UserHandler) GetUserByUsername(w http.ResponseWriter, r *http.Request) {
	// Get username from URL path parameter
	vars := mux.Vars(r)
	username := vars["username"]

	if username == "" {
		http.Error(w, "Username is required", http.StatusBadRequest)
		return
	}

	var user data.User
	ctx := context.Background()
	err := h.db.QueryRow(ctx,
		`SELECT id, username, fullname, email, created_at, updated_at
        FROM users WHERE username = $1`,
		username,
	).Scan(
		&user.Id,
		&user.Username,
		&user.Fullname,
		&user.Email,
		&user.CreatedAt,
		&user.UpdatedAt,
	)
	if err != nil {
		h.l.Println("Database error while fetching user: ", err)
		http.Error(w, "User not found", http.StatusNotFound)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	if err = json.NewEncoder(w).Encode(user); err != nil {
		h.l.Println("Error encoding response:", err)
		http.Error(w, "Internal Server Error", http.StatusInternalServerError)
	}
}

func (h *UserHandler) UpdateUser(w http.ResponseWriter, r *http.Request) {
	authHeader := r.Header.Get("Authorization")
	if authHeader == "" {
		http.Error(w, "Authorization header required", http.StatusUnauthorized)
		return
	}

	tokenStr := strings.TrimPrefix(authHeader, "Bearer ")
	claims, err := data.ValidateAccessToken(tokenStr)
	if err != nil {
		h.l.Println("Invalid token: ", err)
		http.Error(w, "Invalid token", http.StatusUnauthorized)
		return
	}

	var updateReq struct {
		Username string `json:"username"`
		Fullname string `json:"fullname"`
		Email    string `json:"email"`
	}

	if err := utils.ParseRequest(r, &updateReq); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Check if new username or email already exists
	var exists bool
	ctx := context.Background()
	err = h.db.QueryRow(ctx,
		"SELECT EXISTS(SELECT 1 FROM users WHERE (username = $1 OR email = $2) AND id != $3)",
		updateReq.Username,
		updateReq.Email,
		claims.UserId,
	).Scan(&exists)
	if err != nil {
		h.l.Println("Database error while checking credentials: ", err)
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}
	if exists {
		http.Error(w, "Username or email already in use", http.StatusConflict)
		return
	}

	_, err = h.db.Exec(ctx,
		`UPDATE users
        SET username = COALESCE(NULLIF($1, ''), username),
            fullname = COALESCE(NULLIF($2, ''), fullname),
            email = COALESCE(NULLIF($3, ''), email),
            updated_at = $4
        WHERE id = $5`,
		updateReq.Username,
		updateReq.Fullname,
		updateReq.Email,
		time.Now(),
		claims.UserId,
	)
	if err != nil {
		h.l.Println("Database error updating user: ", err)
		http.Error(w, "Failed to update user", http.StatusInternalServerError)
		return
	}

	h.GetUser(w, r) // Return updated user data
}

func (h *UserHandler) UpdatePassword(w http.ResponseWriter, r *http.Request) {
	authHeader := r.Header.Get("Authorization")
	if authHeader == "" {
		http.Error(w, "Authorization header required", http.StatusUnauthorized)
		return
	}

	tokenStr := strings.TrimPrefix(authHeader, "Bearer ")
	claims, err := data.ValidateAccessToken(tokenStr)
	if err != nil {
		h.l.Println("Invalid token: ", err)
		http.Error(w, "Invalid token", http.StatusUnauthorized)
		return
	}

	var pwdReq struct {
		CurrentPassword string `json:"current_password"`
		NewPassword     string `json:"new_password"`
	}

	if err := utils.ParseRequest(r, &pwdReq); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	if len(pwdReq.NewPassword) < 8 {
		http.Error(w, "Password must be at least 8 characters", http.StatusBadRequest)
		return
	}

	// Get current password hash
	var currentHash string
	ctx := context.Background()
	err = h.db.QueryRow(ctx,
		"SELECT password FROM users WHERE id = $1",
		claims.UserId,
	).Scan(&currentHash)
	if err != nil {
		h.l.Println("Database error while fetching user: ", err)
		http.Error(w, "User not found", http.StatusNotFound)
		return
	}

	// Verify current password
	if err := bcrypt.CompareHashAndPassword([]byte(currentHash), []byte(pwdReq.CurrentPassword)); err != nil {
		h.l.Println("Invalid current password: ", err)
		http.Error(w, "Invalid current password", http.StatusUnauthorized)
		return
	}

	// Hash new password
	newHash, err := bcrypt.GenerateFromPassword([]byte(pwdReq.NewPassword), bcrypt.DefaultCost)
	if err != nil {
		h.l.Println("Unable to hash the password: ", err)
		http.Error(w, "Failed to hash password", http.StatusInternalServerError)
		return
	}

	// Update password
	_, err = h.db.Exec(ctx,
		"UPDATE users SET password = $1, updated_at = $2 WHERE id = $3",
		newHash,
		time.Now(),
		claims.UserId,
	)
	if err != nil {
		h.l.Println("Database error updating password: ", err)
		http.Error(w, "Failed to update password", http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusNoContent)
}
