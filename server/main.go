package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/Shreyaskr1409/redpanda/data"
	"github.com/Shreyaskr1409/redpanda/database"
	"github.com/Shreyaskr1409/redpanda/middlewares"
	"github.com/Shreyaskr1409/redpanda/routes"
	"github.com/gorilla/mux"
	"github.com/joho/godotenv"
)

func main() {
	godotenv.Load()
	l := log.New(os.Stdout, "auth: ", log.LstdFlags)
	l.Println("Logging starts")

	data.InitTokenSecrets()

	database.Init(l)
	defer database.Close()
	err := database.Migrate(database.DB, l, context.Background())
	if err != nil {
		l.Fatalln("Error encountered during database migration: ", err)
	}

	router := mux.NewRouter()
	router.UseEncodedPath()
	router.Use(mux.CORSMethodMiddleware(router))
	router.Use(middlewares.LoggingMiddleware(l))

	routes.HandleUserRoutes(router, l, database.DB)

	listen_port := fmt.Sprint(":", os.Getenv("PORT"))
	s := &http.Server{
		Addr:         listen_port,
		Handler:      router,
		IdleTimeout:  120 * time.Second,
		ReadTimeout:  20 * time.Second,
		WriteTimeout: 20 * time.Second,
	}

	go func() {
		err := s.ListenAndServe()
		if err != nil && err != http.ErrServerClosed {
			l.Panic(err)
		}
	}()
	l.Println("Server is listening at port", listen_port)

	shutdownChannel := make(chan os.Signal, 1)
	signal.Notify(shutdownChannel, os.Interrupt, syscall.SIGTERM)

	sig := <-shutdownChannel
	l.Println("Recieved signal for graceful shutdown. signal: ", sig)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	l.Println("Shutdown started")
	s.Shutdown(ctx)
	l.Println("Shutdown successful")
}
