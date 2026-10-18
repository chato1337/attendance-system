package edgesync

import (
	"context"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"sync/atomic"
	"testing"
	"time"

	"attendance-system/edge/internal/cloud"
	"attendance-system/edge/internal/store"
)

func TestPullPushAndReload(t *testing.T) {
	var deltas atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Content-Type", "application/json")
		switch request.URL.Path {
		case "/api/v1/edge/sync/delta/":
			if deltas.Add(1) == 1 {
				_, _ = writer.Write([]byte(`{
					"server_time":"2026-10-18T23:00:00Z","current_version":3,"next_since_version":3,"has_more":false,
					"employees":[{"id":"emp","document_id":"1","first_name":"Ada","last_name":"Lovelace","department_id":null,"is_active":true,"is_inside":false,"version":1}],
					"credentials":[],
					"reader_profiles":[],
					"doors":[{"id":"door-a","node_id":"n","zone_id":null,"name":"A","relay_device_id":"R","direction":"IN","apb_mode":"OFF","face_enabled":false,"required_factors":[],"is_active":true,"version":2}],
					"readers":[]
				}`))
				return
			}
			_, _ = writer.Write([]byte(`{"server_time":"2026-10-18T23:00:02Z","current_version":9,"next_since_version":9,"has_more":false,"employees":[],"credentials":[],"reader_profiles":[],"doors":[{"id":"door-b","node_id":"n","zone_id":null,"name":"B","relay_device_id":"R","direction":"OUT","apb_mode":"OFF","face_enabled":false,"required_factors":[],"is_active":true,"version":9}],"readers":[]}`))
		case "/api/v1/edge/logs/batch/":
			_, _ = writer.Write([]byte(`{"server_time":"2026-10-18T23:00:01Z","accepted":["log-1"],"duplicated":["log-2"],"rejected":[{"id":"log-3","reason":"unknown_door"}]}`))
		case "/api/v1/edge/heartbeat/":
			_, _ = writer.Write([]byte(`{"server_time":"2026-10-18T23:00:03Z","is_online":true}`))
		case "/api/v1/edge/enrollment-reads/":
			writer.WriteHeader(http.StatusCreated)
			_, _ = writer.Write([]byte(`{"id":"e"}`))
		default:
			http.NotFound(writer, request)
		}
	}))
	t.Cleanup(server.Close)
	data := openStore(t)
	ctx := context.Background()
	syncer := New(data, cloud.New(server.URL, "secret"))
	syncer.SkewLimit = time.Hour
	syncer.GatewayConnected = func() bool { return true }
	syncer.Listening = func() []string { return []string{"COM3"} }
	syncer.CommandsConnected = func() bool { return false }
	if err := syncer.Pull(ctx, false); err != nil {
		t.Fatal(err)
	}
	version, err := data.LastVersion(ctx)
	if err != nil || version != 3 {
		t.Fatalf("versión %d %v", version, err)
	}
	if _, err := data.EnqueueEnrollment(ctx, store.EnrollmentSample{ReaderID: "reader", Raw: "AB"}); err != nil {
		t.Fatal(err)
	}
	for _, id := range []string{"log-1", "log-2", "log-3"} {
		if err := data.EnqueueLog(ctx, store.Log{ID: id, Timestamp: time.Now().UTC(), Direction: "IN", Status: "DENIED"}); err != nil {
			t.Fatal(err)
		}
	}
	if err := syncer.Push(ctx); err != nil {
		t.Fatal(err)
	}
	if size, err := data.QueueSize(ctx); err != nil || size != 0 {
		t.Fatalf("cola %d %v", size, err)
	}
	pending, err := data.PendingEnrollment(ctx, 10)
	if err != nil || len(pending) != 0 {
		t.Fatalf("enrolamiento pendiente %d %v", len(pending), err)
	}
	if err := syncer.Beat(ctx); err != nil {
		t.Fatal(err)
	}
	if err := syncer.Pull(ctx, true); err != nil {
		t.Fatal(err)
	}
	if _, ok, err := data.LookupDoor(ctx, "door-a"); err != nil || ok {
		t.Fatalf("la puerta del primer delta sigue: %v %v", ok, err)
	}
	if _, ok, err := data.LookupDoor(ctx, "door-b"); err != nil || !ok {
		t.Fatalf("falta la puerta del reload: %v %v", ok, err)
	}
}

func openStore(t *testing.T) *store.Store {
	t.Helper()
	data, err := store.Open(filepath.Join(t.TempDir(), "agent.db"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = data.Close() })
	return data
}
