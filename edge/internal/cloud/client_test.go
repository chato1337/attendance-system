package cloud

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	"attendance-system/edge/internal/protocol"
	"attendance-system/edge/internal/store"
)

func TestDeltaAndIdempotentPush(t *testing.T) {
	var pushes atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.Header.Get("Authorization") != "Bearer secret" {
			t.Errorf("auth %q", request.Header.Get("Authorization"))
		}
		switch request.URL.Path {
		case "/api/v1/edge/sync/delta/":
			writer.Header().Set("Content-Type", "application/json")
			_, _ = writer.Write([]byte(`{"server_time":"2026-10-18T23:00:00Z","current_version":4,"next_since_version":4,"has_more":false,"employees":[],"credentials":[],"reader_profiles":[],"doors":[],"readers":[]}`))
		case "/api/v1/edge/logs/batch/":
			pushes.Add(1)
			writer.Header().Set("Content-Type", "application/json")
			_, _ = writer.Write([]byte(`{"server_time":"2026-10-18T23:00:01Z","accepted":["a"],"duplicated":[],"rejected":[]}`))
		default:
			http.NotFound(writer, request)
		}
	}))
	t.Cleanup(server.Close)
	client := New(server.URL, "secret")
	page, err := client.Delta(context.Background(), 0)
	if err != nil || page.NextSinceVersion != 4 {
		t.Fatalf("%+v %v", page, err)
	}
	result, err := client.PushLogs(context.Background(), []protocol.Log{{ID: "a", Timestamp: "2026-10-18T10:00:00Z", Direction: "IN", Status: "GRANTED"}})
	if err != nil || len(result.Accepted) != 1 {
		t.Fatalf("%+v %v", result, err)
	}
	if _, err := client.PushLogs(context.Background(), []protocol.Log{{ID: "a", Timestamp: "2026-10-18T10:00:00Z", Direction: "IN", Status: "GRANTED"}}); err != nil {
		t.Fatal(err)
	}
	if pushes.Load() != 2 {
		t.Fatalf("envíos %d", pushes.Load())
	}
}

func TestRetries429(t *testing.T) {
	var hits atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		if hits.Add(1) == 1 {
			writer.Header().Set("Retry-After", "0")
			writer.WriteHeader(http.StatusTooManyRequests)
			return
		}
		writer.Header().Set("Content-Type", "application/json")
		_, _ = writer.Write([]byte(`{"server_time":"2026-10-18T23:00:00Z","current_version":0,"next_since_version":0,"has_more":false,"employees":[],"credentials":[],"reader_profiles":[],"doors":[],"readers":[]}`))
	}))
	t.Cleanup(server.Close)
	client := New(server.URL, "secret")
	if _, err := client.Delta(context.Background(), 0); err != nil {
		t.Fatal(err)
	}
	sample := store.EnrollmentSample{ReaderID: "reader", Raw: "AB"}
	server.Config.Handler = http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.Path != "/api/v1/edge/enrollment-reads/" {
			t.Errorf("ruta %s", request.URL.Path)
		}
		writer.WriteHeader(http.StatusCreated)
		_, _ = writer.Write([]byte(`{"id":"1"}`))
	})
	if err := client.ReportEnrollment(context.Background(), sample); err != nil {
		t.Fatal(err)
	}
}
