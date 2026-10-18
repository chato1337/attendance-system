package store

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	"attendance-system/edge/internal/profile"
	"attendance-system/edge/internal/protocol"
)

func TestDeltaSeedsStateAndFullSyncDropsMissingRows(t *testing.T) {
	ctx := context.Background()
	data := openTest(t)
	page := protocol.Delta{
		Employees: []protocol.Employee{{
			ID: "emp", DocumentID: "1", FirstName: "Ada", LastName: "Lovelace", IsActive: true, IsInside: true, Version: 2,
		}},
		Doors: []protocol.Door{{
			ID: "door-a", Name: "A", RelayDeviceID: "RELAY", Direction: "IN", ApbMode: "OFF", IsActive: true, Version: 3,
		}},
		ReaderProfiles: []protocol.ReaderProfile{{
			ID: "profile", Name: "hex", CredentialType: "RFID", Normalization: []profile.Step{{Op: "trim"}},
			MinLength: 1, MaxLength: 16, IsActive: true, Version: 1,
		}},
	}
	if err := data.ApplyDelta(ctx, page, nil); err != nil {
		t.Fatal(err)
	}
	inside, err := data.State(ctx, "emp")
	if err != nil || !inside {
		t.Fatalf("estado inicial = %v %v", inside, err)
	}
	if err := data.SaveState(ctx, "emp", false, time.Now().UTC()); err != nil {
		t.Fatal(err)
	}
	page.Employees[0].IsInside = true
	page.Employees[0].Version = 4
	if err := data.ApplyDelta(ctx, page, nil); err != nil {
		t.Fatal(err)
	}
	inside, err = data.State(ctx, "emp")
	if err != nil || inside {
		t.Fatalf("el delta pisó el estado local: %v %v", inside, err)
	}

	seen := NewSeen()
	replacement := protocol.Delta{Doors: []protocol.Door{{
		ID: "door-b", Name: "B", RelayDeviceID: "RELAY", Direction: "OUT", ApbMode: "HARD", IsActive: true, Version: 8,
	}}}
	if err := data.ApplyDelta(ctx, replacement, &seen); err != nil {
		t.Fatal(err)
	}
	if err := data.FinishFullSync(ctx, seen); err != nil {
		t.Fatal(err)
	}
	count, err := data.CountDoors(ctx)
	if err != nil || count != 1 {
		t.Fatalf("puertas = %d %v", count, err)
	}
	if _, ok, err := data.LookupDoor(ctx, "door-a"); err != nil || ok {
		t.Fatalf("la puerta vieja sigue: ok=%v err=%v", ok, err)
	}
	if _, exists, err := data.EmployeeActive(ctx, "emp"); err != nil || exists {
		t.Fatalf("el empleado viejo sigue: %v %v", exists, err)
	}
}

func TestQueueIsIdempotent(t *testing.T) {
	ctx := context.Background()
	data := openTest(t)
	stamp := time.Date(2026, 10, 18, 10, 0, 0, 0, time.UTC)
	item := Log{ID: "log-1", Timestamp: stamp, Direction: "IN", Status: "GRANTED", Method: "RFID", Source: "gateway"}
	if err := data.EnqueueLog(ctx, item); err != nil {
		t.Fatal(err)
	}
	if err := data.EnqueueLog(ctx, item); err != nil {
		t.Fatal(err)
	}
	pending, err := data.PendingLogs(ctx, 10)
	if err != nil || len(pending) != 1 {
		t.Fatalf("pendientes = %d %v", len(pending), err)
	}
	if err := data.MarkLogsSent(ctx, []string{"log-1"}, stamp); err != nil {
		t.Fatal(err)
	}
	size, err := data.QueueSize(ctx)
	if err != nil || size != 0 {
		t.Fatalf("cola = %d %v", size, err)
	}
	if err := data.PurgeSent(ctx, stamp.Add(time.Second)); err != nil {
		t.Fatal(err)
	}
	pending, err = data.PendingLogs(ctx, 10)
	if err != nil || len(pending) != 0 {
		t.Fatalf("después de purgar = %d %v", len(pending), err)
	}
}

func openTest(t *testing.T) *Store {
	t.Helper()
	data, err := Open(filepath.Join(t.TempDir(), "agent.db"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = data.Close() })
	return data
}
