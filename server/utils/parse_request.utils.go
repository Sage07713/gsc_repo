package utils

import (
	"encoding/json"
	"net/http"

	"github.com/gorilla/schema"
)

func ParseRequest(r *http.Request, dst interface{}) error {
	if r.Header.Get("Content-Type") == "application/json" {
		return json.NewDecoder(r.Body).Decode(dst)
	}
	if r.Header.Get("Content-Type") == "application/x-www-form-urlencoded" {
		err := r.ParseForm()
		if err != nil {
			return err
		}
		return schema.NewDecoder().Decode(dst, r.PostForm)
	}
	if r.Header.Get("Content-Type") == "multipart/form-data" {
		err := r.ParseMultipartForm(10 << 20)
		if err != nil {
			return err
		}
		return schema.NewDecoder().Decode(dst, r.MultipartForm.Value)
	}
	return nil
}
