package routes

import (
	"log"

	"github.com/Shreyaskr1409/redpanda/handlers"
	"github.com/Shreyaskr1409/redpanda/middlewares"
	"github.com/gorilla/mux"
	"github.com/jackc/pgx/v5/pgxpool"
)

func HandleUserRoutes(router *mux.Router, l *log.Logger, db *pgxpool.Pool) {
	userHandler := handlers.NewUserHandler(l, db)
	authMiddlewareHandler := middlewares.AuthMiddleware(db)

	userRouter := router.PathPrefix("/api/v1/users").Subrouter()

	userRouter.HandleFunc("/user", userHandler.GetUser).Methods("GET")
	userRouter.HandleFunc("/register", userHandler.Register).Methods("POST")
	userRouter.HandleFunc("/login", userHandler.Login).Methods("POST")

	authUserRouter := userRouter.NewRoute().Subrouter()
	authUserRouter.Use(authMiddlewareHandler)

	authUserRouter.HandleFunc("/logout", userHandler.Logout).Methods("GET")
	authUserRouter.HandleFunc("/update", userHandler.UpdateUser).Methods("PATCH")
	authUserRouter.HandleFunc("/update-password", userHandler.UpdatePassword).Methods("PATCH")

	// need to put this at last always
	userRouter.HandleFunc("/{username}", userHandler.GetUserByUsername).Methods("GET")
}
