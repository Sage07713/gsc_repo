package database

import (
	"context"
	"log"
	"os"

	"github.com/jackc/pgx/v5/pgxpool"
)

var DB *pgxpool.Pool

func Init(l *log.Logger) {
	l.Println("Connecting to the database...")
	dbUrl := os.Getenv("DBURL")
	if dbUrl == "" {
		l.Fatal("DBURL environment variable not set")
	}

	conn, err := pgxpool.New(context.Background(), dbUrl)
	if err != nil {
		log.Fatalf("Unable to create a connection pool: %v", err)
	}
	DB = conn
	l.Println("Connected to the database!")
}

func Close() {
	DB.Close()
}
