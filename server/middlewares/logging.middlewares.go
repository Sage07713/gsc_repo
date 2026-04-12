package middlewares

import (
	"log"
	"net/http"
)

func LoggingMiddleware(l *log.Logger) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			l.Printf("%s %s", r.Method, r.RequestURI)
			next.ServeHTTP(w, r)
		})
	}
}
