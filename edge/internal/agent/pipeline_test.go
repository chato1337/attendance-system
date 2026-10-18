package agent

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	"attendance-system/edge/internal/engine"
	"attendance-system/edge/internal/gateway"
	"attendance-system/edge/internal/gatewaysim"
	"attendance-system/edge/internal/profile"
	"attendance-system/edge/internal/protocol"
	"attendance-system/edge/internal/store"
)

func TestSimulatedReadOpensTheRelay(t *testing.T) {
	sim, err := gatewaysim.Start()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = sim.Close() })
	data, err := store.Open(filepath.Join(t.TempDir(), "agent.db"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = data.Close() })
	if err := data.ApplyDelta(context.Background(), protocol.Delta{
		ReaderProfiles: []protocol.ReaderProfile{{
			ID: "profile", Name: "hex", CredentialType: "RFID",
			Normalization: []profile.Step{{Op: "trim"}, {Op: "upper"}, {Op: "pad_left", Length: 8, Char: "0"}},
			MinLength:     8, MaxLength: 8, IsActive: true, Version: 1,
		}},
		Employees:   []protocol.Employee{{ID: "emp", DocumentID: "1", FirstName: "Ada", LastName: "Lovelace", IsActive: true, Version: 2}},
		Credentials: []protocol.Credential{{ID: "cred", EmployeeID: "emp", Type: "RFID", Payload: "0000AB12", IsActive: true, Version: 3}},
		Doors:       []protocol.Door{{ID: "door", Name: "Principal", RelayDeviceID: "RELAY1", Direction: "IN", ApbMode: "OFF", IsActive: true, Version: 4}},
		Readers:     []protocol.Reader{{ID: "reader", DoorID: "door", ReaderProfileID: "profile", Name: "Lector", ReaderDeviceID: "COM3", IsActive: true, Version: 5}},
	}, nil); err != nil {
		t.Fatal(err)
	}
	client := gateway.New(sim.URL, gateway.Options{MinBackoff: 20 * time.Millisecond, MaxBackoff: 40 * time.Millisecond, OpenTimeout: time.Second})
	client.SetDevices([]string{"COM3"})
	eng := engine.New(data, client, nil, nil)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	go func() { _ = client.Run(ctx) }()
	go func() {
		for {
			select {
			case <-ctx.Done():
				return
			case event := <-client.Events():
				eng.Handle(ctx, engine.Event{Source: engine.SourceGateway, DeviceID: event.DeviceID, Raw: event.Data, At: event.At})
			}
		}
	}()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) && !contains(sim.Listened(), "COM3") {
		time.Sleep(15 * time.Millisecond)
	}
	sim.Inject("COM3", "ab12")
	deadline = time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		pending, err := data.PendingLogs(context.Background(), 5)
		if err != nil {
			t.Fatal(err)
		}
		if len(pending) == 1 && pending[0].Status == "GRANTED" {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatal("la lectura no concedió el acceso")
}

func contains(values []string, want string) bool {
	for _, value := range values {
		if value == want {
			return true
		}
	}
	return false
}
